"""Serialized activation lifecycle, independent from Tk and Windows hotkeys."""
from dataclasses import dataclass, field
from enum import StrEnum
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from aria.permissions import ConfirmationRequired, PermissionDenied
from aria.voice import Timeline


class State(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    EXECUTING = "EXECUTING"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


@dataclass
class ConfirmationPrompt:
    pending: object
    timeline: Timeline
    done: threading.Event = field(default_factory=threading.Event)
    answer: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def respond(self, answer):
        with self._lock:
            if self.done.is_set():
                return
            self.answer = answer
            self.timeline.mark("confirmation_response")
            self.done.set()


class ActivationController:
    def __init__(self, engine, voice, publish):
        self.engine, self.voice, self.publish = engine, voice, publish
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aria-command")
        self.lock = threading.Lock()
        self.busy = False
        self.closed = False
        self.prompt = None
        self.last_timeline = None
        self.last_status = None
        self.log = logging.getLogger("aria.activation")

    def activate(self, hotkey_time=None, foreground=None):
        with self.lock:
            if self.busy or self.closed:
                return False
            self.busy = True
        line = Timeline()
        line.mark("hotkey_press", hotkey_time if hotkey_time is not None else time.perf_counter())
        self.pool.submit(self._run, line, foreground)
        return True

    def _state(self, name, message="", line=None):
        self.last_status = (State(name), message)
        self.publish("state", (State(name), message, line))

    def _run(self, line, foreground):
        # pycaw/COM objects are created and used on this same worker.
        import ctypes
        ctypes.windll.ole32.CoInitialize(None)
        try:
            self.engine.cancel(reason="superseded")
            _, action, line = self.voice.prepare(line, lambda name: self._state(name, line=line))
            if self.closed:
                return
            if action.target == "foreground":
                if not self.engine.windows.exists(foreground):
                    raise LookupError("The window active when you pressed the hotkey disappeared")
                self.engine.activation_window = foreground

            def event(name):
                line.mark(name)
                if name == "action_start":
                    self._state(State.EXECUTING, line=line)
            try:
                result = self.engine.execute(action, on_event=event)
            except ConfirmationRequired as exc:
                prompt = ConfirmationPrompt(exc.pending, line)
                self.prompt = prompt
                self._state(State.CONFIRMATION_REQUIRED, line=line)
                self.publish("confirmation", prompt)
                remaining = max(0, exc.pending.expires_at-self.engine.permissions.clock())
                prompt.done.wait(remaining)
                if not prompt.done.is_set():
                    prompt.respond("timed_out")
                if self.closed or prompt.answer != "confirmed":
                    reason = prompt.answer or "cancelled"
                    self.engine.cancel(exc.pending.token, reason=reason)
                    self.publish("dismiss", prompt)
                    raise PermissionDenied("Confirmation timed out; nothing was executed" if reason == "timed_out" else "Confirmation cancelled; nothing was executed")
                result = self.engine.confirm(exc.pending.token, on_event=event)
            self._state(State.SUCCESS, result.message, line)
        except Exception as exc:
            self.log.exception("command_failed")
            message = str(exc) if isinstance(exc, (ValueError, LookupError, OSError, RuntimeError)) else "Command failed; see the diagnostic log"
            self._state(State.ERROR, message[:500], line)
        finally:
            self.engine.activation_window = None
            self.prompt = None
            self.last_timeline = line
            self.log.info("command_timing_ms=%s", line.milliseconds())
            self.log.info("command_event_offsets_ms=%s", {
                key: round((value-line.events["hotkey_press"])*1000, 3)
                for key,value in line.events.copy().items()
            })
            ctypes.windll.ole32.CoUninitialize()
            # UI schedules a short status display, then calls ready().
            self.publish("complete", line)

    def ready(self):
        with self.lock:
            if not self.closed:
                self._state(State.IDLE)
            self.busy = False

    def close(self):
        self.closed = True
        if self.prompt:
            self.prompt.respond("cancelled")
        self.engine.cancel()
        self.pool.shutdown(wait=False, cancel_futures=True)
