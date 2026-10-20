"""Presentation-only event contract for the Phase 8 Shard prototype.

This module has no reference to the command engine or operating-system adapters.
"""

from dataclasses import dataclass
from enum import StrEnum
import queue


class DisplayState(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PARTIAL = "PARTIAL"
    FINAL = "FINAL"
    PROCESSING = "PROCESSING"
    CONFIRMATION = "CONFIRMATION"
    EXECUTING = "EXECUTING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNVERIFIED = "UNVERIFIED"


class OutcomeStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNVERIFIED = "UNVERIFIED"


TERMINAL = frozenset({DisplayState.VERIFIED, DisplayState.FAILED,
                      DisplayState.CANCELLED, DisplayState.UNVERIFIED})
TRANSITIONS = {
    DisplayState.IDLE: frozenset({DisplayState.LISTENING}),
    DisplayState.LISTENING: frozenset({DisplayState.PARTIAL, DisplayState.FINAL,
                                      DisplayState.PROCESSING, DisplayState.FAILED,
                                      DisplayState.CANCELLED}),
    DisplayState.PARTIAL: frozenset({DisplayState.PARTIAL, DisplayState.FINAL,
                                    DisplayState.PROCESSING, DisplayState.FAILED,
                                    DisplayState.CANCELLED}),
    DisplayState.FINAL: frozenset({DisplayState.PROCESSING, DisplayState.CONFIRMATION,
                                  DisplayState.EXECUTING, DisplayState.FAILED,
                                  DisplayState.CANCELLED}),
    DisplayState.PROCESSING: frozenset({DisplayState.CONFIRMATION, DisplayState.EXECUTING,
                                       DisplayState.FAILED, DisplayState.CANCELLED}),
    DisplayState.CONFIRMATION: frozenset({DisplayState.EXECUTING, DisplayState.FAILED,
                                         DisplayState.CANCELLED}),
    DisplayState.EXECUTING: TERMINAL,
    **{state: frozenset({DisplayState.IDLE}) for state in TERMINAL},
}


@dataclass(frozen=True, slots=True)
class DisplayEvent:
    session_id: str
    sequence: int
    state: DisplayState
    transcript_revision: int | None = None
    transcript: str | None = None
    outcome: OutcomeStatus | None = None
    # Explicit producer admission of a newer activation; no implicit preemption.
    supersedes: str | None = None


@dataclass(frozen=True, slots=True)
class PresentationSnapshot:
    session_id: str | None = None
    sequence: int = -1
    state: DisplayState = DisplayState.IDLE
    transcript_revision: int = -1
    transcript: str = ""
    outcome: OutcomeStatus | None = None


class PresentationModel:
    """Reject invalid events; never infer an outcome from a generic result."""

    def __init__(self):
        self.snapshot = PresentationSnapshot()
        self._seen_sessions: set[str] = set()
        self.closed = False

    def apply(self, event: DisplayEvent) -> bool:
        if self.closed or not self._valid(event):
            return False
        current = self.snapshot
        new_session = event.session_id != current.session_id
        if new_session:
            if event.session_id in self._seen_sessions:
                return False
            if event.sequence != 0 or event.state != DisplayState.LISTENING:
                return False
            if current.state not in TERMINAL | {DisplayState.IDLE} and event.supersedes != current.session_id:
                return False
            if event.supersedes is not None and event.supersedes != current.session_id:
                return False
            self._seen_sessions.add(event.session_id)
            current = PresentationSnapshot()
        else:
            if event.supersedes is not None:
                return False
            if event.sequence != current.sequence + 1:
                return False
            if event.state not in TRANSITIONS[current.state]:
                return False

        revision = current.transcript_revision
        transcript = current.transcript
        if event.transcript is not None:
            if event.state == DisplayState.PARTIAL and event.transcript_revision <= revision:
                return False
            if event.state == DisplayState.FINAL and event.transcript_revision < revision:
                return False
            revision, transcript = event.transcript_revision, event.transcript
        elif event.state == DisplayState.FINAL:
            # Final without real text is legitimate; never display a stale partial as final.
            revision, transcript = -1, ""

        self.snapshot = PresentationSnapshot(event.session_id, event.sequence, event.state,
                                             revision, transcript, event.outcome)
        return True

    @staticmethod
    def _valid(event: DisplayEvent) -> bool:
        if type(event) is not DisplayEvent or type(event.session_id) is not str or not event.session_id:
            return False
        if type(event.sequence) is not int or event.sequence < 0 or type(event.state) is not DisplayState:
            return False
        if event.supersedes is not None and (type(event.supersedes) is not str or not event.supersedes):
            return False
        if event.state in TERMINAL:
            if type(event.outcome) is not OutcomeStatus or event.outcome != OutcomeStatus(event.state.value):
                return False
        elif event.outcome is not None:
            return False
        if event.transcript is None:
            return event.transcript_revision is None
        if event.state not in {DisplayState.PARTIAL, DisplayState.FINAL}:
            return False
        return (type(event.transcript) is str and type(event.transcript_revision) is int
                and event.transcript_revision >= 0 and len(event.transcript) <= 10000)

    def close(self):
        self.closed = True
        self.snapshot = PresentationSnapshot()
        self._seen_sessions.clear()


class PresentationInbox:
    """Optional bounded UI-thread drain; no polling or execution authority."""

    def __init__(self, model=None, source=None):
        self.model = model if model is not None else PresentationModel()
        self.source = source if source is not None else queue.Queue(maxsize=256)
        self.error: str | None = None
        self.closed = False

    def submit(self, event):
        if self.closed or self.error:
            return False
        try:
            self.source.put_nowait(event)
            return True
        except Exception:
            self.error = "Display event source unavailable"
            return False

    def drain(self, limit=256):
        if self.closed or self.error:
            return 0
        accepted = 0
        try:
            for _ in range(limit):
                try:
                    event = self.source.get_nowait()
                except queue.Empty:
                    break
                accepted += self.model.apply(event)
        except Exception:
            self.error = "Display event source unavailable"
        return accepted

    def close(self):
        self.closed = True
        self.model.close()
        try:
            for _ in range(256):
                self.source.get_nowait()
        except Exception:
            pass
