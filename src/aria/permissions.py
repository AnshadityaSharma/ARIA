"""Deterministic permissions and single-use action-bound confirmations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import logging
import math
import secrets
import threading
import time
from pathlib import Path

from aria.core import Action, ActionType as T, RISK, Risk


class Decision(StrEnum):
    ALLOW = "ALLOW"
    CONFIRM = "CONFIRM"
    DENY = "DENY"


class PermissionDenied(ValueError):
    pass


@dataclass(frozen=True)
class Pending:
    token: str
    action: Action
    expires_at: float
    description: str


class ConfirmationRequired(RuntimeError):
    def __init__(self, pending: Pending):
        self.pending = pending
        super().__init__(pending.description)


class PermissionEngine:
    def __init__(self, timeout=30.0, confirm_low=False, clock=time.monotonic):
        if not math.isfinite(timeout) or not 0.05 <= timeout <= 600:
            raise ValueError("Confirmation timeout must be between 0.05 and 600 seconds")
        self.timeout, self.confirm_low, self.clock = timeout, confirm_low, clock
        self._pending = None
        self._lock = threading.Lock()
        self.log = logging.getLogger("aria.permissions")

    def evaluate(self, action) -> Decision:
        try:
            if type(action) is not Action:
                return Decision.DENY
            action.validate()
            risk = RISK[action.kind]
        except (ValueError, TypeError, KeyError):
            return Decision.DENY
        if risk in {Risk.MEDIUM, Risk.HIGH} or (self.confirm_low and risk == Risk.LOW):
            return Decision.CONFIRM
        return Decision.ALLOW

    def cancel(self, token=None, reason="cancelled"):
        with self._lock:
            if self._pending and (token is None or secrets.compare_digest(token, self._pending.token)):
                self.log.info("confirmation_%s action=%s", reason, self._pending.action.kind)
                self._pending = None

    def request(self, action: Action) -> Pending:
        if self.evaluate(action) != Decision.CONFIRM:
            raise PermissionDenied("Only validated confirmation-required actions can be presented")
        with self._lock:
            self._pending = Pending(secrets.token_urlsafe(32), action, self.clock() + self.timeout, describe(action))
            self.log.info("confirmation_requested action=%s target=%s", action.kind, action.target)
            return self._pending

    def consume(self, token: str) -> Action:
        with self._lock:
            pending = self._pending
            if not isinstance(token, str) or not token.isascii() or pending is None or not secrets.compare_digest(token, pending.token):
                raise PermissionDenied("This confirmation is no longer valid")
            self._pending = None
            if self.clock() >= pending.expires_at:
                self.log.info("confirmation_timed_out action=%s", pending.action.kind)
                raise PermissionDenied("Confirmation timed out; nothing was executed")
            if self.evaluate(pending.action) == Decision.DENY:
                raise PermissionDenied("Action is no longer valid")
            self.log.info("confirmation_confirmed action=%s", pending.action.kind)
            return pending.action


def describe(action: Action) -> str:
    descriptions = {
        T.DELETE_PATH: ("Delete file or folder", "This item will be moved to the Recycle Bin."),
        T.MOVE_PATH: ("Move file or folder", "The item will move to the destination shown. Existing items will not be overwritten."),
        T.RENAME_PATH: ("Rename file or folder", "The item will receive the destination name shown. Existing items will not be overwritten."),
        T.SHUTDOWN: ("Shut down computer", "Windows will shut down and unsaved work may be affected."),
        T.DOWNLOAD_FILE: ("Download file", "The browser will save the selected file to local storage."),
    }
    label, consequence = descriptions.get(action.kind, (action.kind.value.replace("_", " ").title(), "This operation will change the specified target."))
    parts = ["ARIA needs confirmation", f"Action: {label}"]
    if action.target:
        parts.append(f"Target: {action.target}")
    if "destination" in action.params:
        destination = action.params["destination"]
        if action.kind == T.RENAME_PATH:
            destination = str(Path(action.target).with_name(destination))
        parts.append(f"Destination: {destination}")
    parts.append(f"Consequence: {consequence}")
    return "\n\n".join(parts)
