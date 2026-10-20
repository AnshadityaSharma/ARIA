"""Seam projection, activity contract and motion. No Tk, voice or engine imports."""
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
import math
import queue
import threading
import time

from aria.shard_presentation import (DisplayEvent, DisplayState as S, OutcomeStatus,
                                     PresentationInbox, PresentationSnapshot)

LABELS = {S.IDLE: "Ready", S.LISTENING: "Listening", S.PARTIAL: "Listening",
          S.FINAL: "Heard", S.PROCESSING: "Waiting for result",
          S.CONFIRMATION: "Confirmation needed", S.EXECUTING: "Action in progress",
          S.VERIFIED: "Verified", S.FAILED: "Action failed",
          S.CANCELLED: "Cancelled", S.UNVERIFIED: "Result not verified"}
ICONS = {S.PROCESSING: "…", S.CONFIRMATION: "!", S.EXECUTING: "↗",
         S.VERIFIED: "✓", S.FAILED: "!", S.CANCELLED: "−", S.UNVERIFIED: "?"}
ATTENTION = frozenset({S.CONFIRMATION, S.FAILED, S.UNVERIFIED})


class ActivityKind(StrEnum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """Optional bounded envelope, not speech, transcript or an execution state.

    Sequence is independent for each kind within the current admitted session.
    The output envelope never changes or erases the command's explicit outcome.
    """
    session_id: str
    sequence: int
    kind: ActivityKind
    level: float


@dataclass(frozen=True, slots=True)
class WorkArea:
    left: int
    top: int
    right: int
    bottom: int
    dpi: int = 96

    @property
    def scale(self):
        return max(.75, min(4., self.dpi / 96))


def placement(area, width, height, below=0):
    """Clamp complete windows, including tiny/negative-origin work areas."""
    if area.right <= area.left or area.bottom <= area.top:
        raise ValueError("Empty monitor work area")
    width = min(max(1, round(width * area.scale)), area.right - area.left)
    height = min(max(1, round(height * area.scale)), area.bottom - area.top)
    x = area.left + (area.right - area.left - width) // 2
    y = min(area.bottom - height, max(area.top, area.top + round(below * area.scale)))
    return x, y, width, height


@dataclass(frozen=True, slots=True)
class SeamFrame:
    snapshot: PresentationSnapshot
    compact_state: S
    expanded: bool
    activity: float = 0.
    speaking: bool = False
    fault: str | None = None


class SeamAdapter:
    """Worker-safe submit; UI-thread-only advance/disclosure. Bounded work.

    Caller schedules advance every 20ms; render only on a changed frame.
    Polling is separate from animation and never invokes a command callback.
    """
    def __init__(self, clock=time.perf_counter, inbox=None):
        self.clock = clock
        self.inbox = inbox if inbox is not None else PresentationInbox()
        self.activity_queue = queue.Queue(maxsize=64)
        self.activity_seq = {}
        self.activity_value = {}
        self.lock = threading.Lock()
        self.received = {}
        self.latencies_ms = deque(maxlen=512)
        self.latest = self.inbox.model.snapshot
        self.latest_received_at = None
        self.compact_state = S.IDLE
        self.pending = None
        self.return_at = None
        self.pinned = False
        self.hover = False
        self.dismissed = False
        self.hidden = False
        self.closed = False
        self.fault = None
        self.last_frame = None
        self.rejected_activity = 0

    def submit(self, event):
        with self.lock:
            if self.closed:
                return False
            # Only bounded metadata, never a persistent transcript log.
            if (type(event) is DisplayEvent and type(event.session_id) is str
                    and type(event.sequence) is int and len(self.received) < 256):
                self.received[(event.session_id, event.sequence)] = self.clock()
            return self.inbox.submit(event)

    def submit_activity(self, event):
        with self.lock:
            if self.closed:
                return False
            if (type(event) is not ActivityEvent or type(event.session_id) is not str or
                    not event.session_id or type(event.sequence) is not int or event.sequence < 0 or
                    type(event.kind) is not ActivityKind or type(event.level) not in (float, int) or
                    not math.isfinite(event.level) or not 0 <= event.level <= 1):
                return False
            try:
                self.activity_queue.put_nowait(event)
                return True
            except queue.Full:
                # Losing activity cannot lose or authorize a command outcome.
                return False

    def advance(self):
        if self.closed:
            return None
        now = self.clock()
        self.inbox.drain(256)
        snap = self.inbox.model.snapshot
        if snap != self.latest:
            new_session = snap.session_id != self.latest.session_id
            self.latest = snap
            self.dismissed = False
            self.return_at = None
            if new_session:
                self.activity_seq.clear()
                self.activity_value.clear()
                self.pinned = False
            if snap.state in {S.PROCESSING, S.EXECUTING}:
                # Source state is immediate; only its visual exposure is gated.
                self.pending = (now + .180, snap)
            else:
                self.pending = None
                self.compact_state = snap.state
                if snap.state in {S.VERIFIED, S.CANCELLED}:
                    self.return_at = now + (1.3 if snap.state == S.VERIFIED else .45)
            with self.lock:
                received = self.received.get((snap.session_id, snap.sequence))
                self.received.clear()
            if received is not None and snap.state not in {S.PROCESSING, S.EXECUTING}:
                self.latencies_ms.append((now - received) * 1000)
            self.latest_received_at = received
        if self.pending and now >= self.pending[0]:
            if self.pending[1] == self.latest:
                self.compact_state = self.latest.state
            self.pending = None
        if self.return_at and now >= self.return_at:
            self.compact_state = S.IDLE
            self.return_at = None
        for _ in range(64):
            try:
                activity = self.activity_queue.get_nowait()
            except queue.Empty:
                break
            if (activity.session_id != snap.session_id or
                    activity.sequence <= self.activity_seq.get(activity.kind, -1)):
                self.rejected_activity += 1
                continue
            self.activity_seq[activity.kind] = activity.sequence
            self.activity_value[activity.kind] = (activity.level, now)
        # Envelopes expire if an external signal stops publishing; never idle-loop forever.
        def level(kind):
            value, stamp = self.activity_value.get(kind, (0., -math.inf))
            return value if now - stamp <= .25 else 0.
        input_level = level(ActivityKind.INPUT) if snap.state in {S.LISTENING, S.PARTIAL} else 0.
        output_level = level(ActivityKind.OUTPUT) if snap.state != S.CONFIRMATION else 0.
        self.fault = self.inbox.error
        frame = SeamFrame(snap, self.compact_state,
                          self.pinned or self.hover or (not self.dismissed and (snap.state in ATTENTION or bool(self.fault))),
                          max(input_level, output_level), output_level > 0, self.fault)
        if self.hidden or frame == self.last_frame:
            return None
        self.last_frame = frame
        return frame

    def dismiss(self):
        self.dismissed = True
        self.pinned = self.hover = False

    def close(self):
        with self.lock:
            self.closed = True
            self.inbox.close()
            self.received.clear()
        self.activity_value.clear()
        while not self.activity_queue.empty():
            self.activity_queue.get_nowait()
        self.latest = PresentationSnapshot()
        self.last_frame = None


class SeamMotion:
    """Retargetable critically damped springs. Call only while unsettled."""
    def __init__(self):
        self.value = {"width": 124., "beam": 26., "offset": 0.}
        self.velocity = dict.fromkeys(self.value, 0.)
        self.target = self.value.copy()

    def retarget(self, frame, caption=True):
        active = frame.compact_state not in {S.IDLE, S.CANCELLED}
        self.target.update(width=218. if active and caption else 124.,
                           beam=16. if frame.compact_state == S.VERIFIED else 10. if frame.compact_state == S.PROCESSING else 26. + 18 * frame.activity,
                           offset=12. if frame.compact_state == S.EXECUTING else 4 * frame.activity if frame.speaking else -3 * frame.activity)

    def step(self, seconds, reduced=False):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid frame interval")
        dt = min(.025, seconds)
        moving = False
        for key in self.value:
            if reduced:
                self.value[key] = self.target[key]
                self.velocity[key] = 0.
                continue
            w = 34.
            # Exact critically damped integration stays stable after a slow frame.
            delta = self.value[key] - self.target[key]
            impulse = (self.velocity[key] + w*delta)*dt
            decay = math.exp(-w*dt)
            self.value[key] = self.target[key] + (delta+impulse)*decay
            self.velocity[key] = (self.velocity[key]-w*impulse)*decay
            if abs(self.target[key]-self.value[key]) < .01 and abs(self.velocity[key]) < .05:
                self.value[key] = self.target[key]
                self.velocity[key] = 0.
            else:
                moving = True
        return moving
