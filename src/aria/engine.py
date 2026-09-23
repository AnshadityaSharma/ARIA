from __future__ import annotations

import logging
import time
import threading
from pathlib import Path

from aria.core import Action, ActionType as T, Rect, Result, WindowState
from aria.desktop import Applications, Files, Volume, screenshot
from aria.parser import parse
from aria.windows import WindowManager, target_rect
from aria.permissions import ConfirmationRequired, PermissionEngine, PermissionDenied, Decision


class Engine:
    def __init__(self, windows=None, applications=None, files=None, volume=None, permissions=None, shutdown=None,
                 browser_factory=None):
        self.windows = windows or WindowManager(); self.applications = applications or Applications()
        self.files = files or Files(); self.volume = volume or Volume(); self.state = WindowState()
        self.permissions = permissions or PermissionEngine()
        self._execution_lock = threading.RLock()
        self._pending_identity = None
        self.activation_window = None
        self._browser = None
        self._browser_factory = browser_factory
        if shutdown is None:
            from aria.desktop import shutdown_computer
            shutdown = shutdown_computer
        self._shutdown = shutdown

    def run_text(self, text: str) -> Result:
        self.cancel()
        started = time.perf_counter(); action = parse(text)
        result = self.execute(action)
        logging.getLogger("aria").info("action=%s ok=%s elapsed_ms=%.3f", action.kind, result.ok, (time.perf_counter()-started)*1000)
        return result

    def _handle(self, target: str | None) -> int:
        if target == "foreground" or target is None:
            return self.activation_window or self.windows.active()
        if target in {"tracked", "it", "that"}:
            if self.windows.exists(self.state.handle): return self.state.handle
            self.state = WindowState()
            raise LookupError("The tracked window is unavailable; name a window or say 'this window'")
        return self.windows.find(target)

    def _track(self, handle: int, action: T | None = None) -> Rect:
        rect = self.windows.rect(handle); self.state.update(handle, self.windows.title(handle), rect, action); return rect

    def cancel(self, token=None, reason="cancelled"):
        with self._execution_lock:
            self.permissions.cancel(token, reason)

    def _prepare(self, action):
        if self.permissions.evaluate(action) == Decision.DENY:
            raise PermissionDenied("Unsupported or malformed action")
        if action.kind in {T.OPEN_WEBSITE, T.NAVIGATE_BROWSER}:
            from aria.browser import normalize_url
            action = Action(action.kind, normalize_url(action.target), dict(action.params)).validate()
        if action.kind == T.CREATE_FOLDER:
            name = action.params["name"]
            if Path(name).name != name or name in {".", ".."}:
                raise PermissionDenied("Folder name must be a single name")
            action = Action(action.kind, str(self.files.resolve(action.target)), dict(action.params))
        if action.kind == T.TAKE_SCREENSHOT:
            from datetime import datetime
            from aria.desktop import known_folder
            path = self.files.resolve(action.target) if action.target else known_folder("pictures") / f"ARIA-{datetime.now():%Y%m%d-%H%M%S-%f}.png"
            if path.exists():
                raise FileExistsError("Screenshot destination already exists")
            action = Action(action.kind, str(path))
        if action.kind in {T.DELETE_PATH, T.MOVE_PATH, T.RENAME_PATH, T.COPY_PATH}:
            source = self.files.resolve(action.target)
            if not source.exists():
                raise FileNotFoundError(f"Target does not exist: {source}")
            if source == Path(source.anchor):
                raise PermissionDenied("A drive root cannot be a file-operation target")
            params = dict(action.params)
            if action.kind in {T.COPY_PATH, T.MOVE_PATH}:
                destination = self.files.resolve(params["destination"])
                if destination.exists():
                    raise FileExistsError("Destination already exists; overwriting is not supported")
                if source == destination or source in destination.parents:
                    raise PermissionDenied("Destination must be outside the source")
                params["destination"] = str(destination)
            if action.kind == T.RENAME_PATH:
                name = params["destination"]
                if Path(name).name != name or name in {".", ".."}:
                    raise PermissionDenied("Rename requires a filename, not a path")
                if source.with_name(name).exists():
                    raise FileExistsError("Destination already exists")
            action = Action(action.kind, str(source), params).validate()
        return action

    @staticmethod
    def _identity(action):
        if action.kind not in {T.DELETE_PATH, T.MOVE_PATH, T.RENAME_PATH}:
            return None
        stat = Path(action.target).stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

    def execute(self, action: Action, *, on_event=None) -> Result:
        event = on_event or (lambda name: None)
        with self._execution_lock:
            self.cancel()
            action = self._prepare(action)
            decision = self.permissions.evaluate(action)
            event("risk_decision")
            if decision == Decision.CONFIRM:
                self._pending_identity = self._identity(action)
                raise ConfirmationRequired(self.permissions.request(action))
            if decision != Decision.ALLOW:
                raise PermissionDenied("Action denied")
            return self.__dispatch(action, event)

    def confirm(self, token: str, *, on_event=None) -> Result:
        with self._execution_lock:
            action = self.permissions.consume(token)
            if self._identity(action) != self._pending_identity:
                raise PermissionDenied("Target changed since confirmation was requested; repeat the command")
            action = self._prepare(action)
            return self.__dispatch(action, on_event or (lambda name: None))

    def __dispatch(self, action, event):
        event("action_start")
        started = time.perf_counter()
        try:
            result = self.__perform(action, event)
            event("action_complete")
            logging.getLogger("aria").info("action=%s success=true elapsed_ms=%.3f", action.kind, (time.perf_counter()-started)*1000)
            return result
        except Exception:
            logging.getLogger("aria").exception("action=%s execution_failed", action.kind)
            raise

    def __perform(self, action: Action, event) -> Result:
        k = action.kind
        browser_actions = {T.OPEN_BROWSER, T.OPEN_WEBSITE, T.NAVIGATE_BROWSER, T.SEARCH_WEB,
                           T.SEARCH_YOUTUBE, T.PLAY_YOUTUBE, T.TYPE_IN_BROWSER,
                           T.CLICK_BROWSER_ELEMENT, T.SUBMIT_BROWSER, T.DOWNLOAD_FILE}
        if k in browser_actions:
            if self._browser is None:
                if self._browser_factory is None:
                    from aria.browser import BrowserManager
                    self._browser = BrowserManager(files=self.files)
                else:
                    self._browser = self._browser_factory()
            return self._browser.execute(action, event)
        if k == T.SHUTDOWN:
            self._shutdown()
            return Result(True, "Windows shutdown requested")
        if k == T.OPEN_APPLICATION:
            before = {w.handle for w in self.windows.windows()}; self.applications.launch(action.target)
            handle = self.windows.wait_for(action.target, before); self._track(handle, k)
            return Result(True, f"Opened {action.target}", {"handle": handle})
        if k in {T.FOCUS_WINDOW, T.MINIMIZE_WINDOW, T.MAXIMIZE_WINDOW, T.RESTORE_WINDOW, T.RESIZE_WINDOW, T.MOVE_WINDOW}:
            handle = self._handle(action.target)
            requested = None
            if k == T.FOCUS_WINDOW: self.windows.focus(handle)
            elif k in {T.MINIMIZE_WINDOW, T.MAXIMIZE_WINDOW, T.RESTORE_WINDOW}: self.windows.show(handle, k.value.split("_")[0].lower())
            else:
                current = self.windows.rect(handle); work = self.windows.work_area(handle)
                rect = target_rect(current, work, scale=action.params.get("scale"), ratio=action.params.get("screen_ratio"), position=action.params.get("position"), pixels=action.params.get("pixels", 50))
                requested = rect
                self.windows.place(handle, rect)
            geometry = self._track(handle, k)
            constrained = requested is not None and any(abs(a-b)>2 for a,b in zip(
                (geometry.x,geometry.y,geometry.width,geometry.height),
                (requested.x,requested.y,requested.width,requested.height)))
            message = f"Windows/application constrained this request; actual rectangle is ({geometry.x}, {geometry.y}, {geometry.width}, {geometry.height})" if constrained else f"Completed {k}"
            return Result(True, message, {"geometry": geometry, "constrained": constrained})
        if k == T.CREATE_FOLDER:
            path = self.files.create_folder(action.target, action.params["name"]); return Result(True, f"Created {path}")
        if k == T.OPEN_PATH:
            path = self.files.open(action.target); return Result(True, f"Opened {path}")
        if k == T.TAKE_SCREENSHOT:
            path = screenshot(action.target); return Result(True, f"Saved screenshot to {path}")
        if k == T.SET_VOLUME: level = self.volume.set(action.params["level"]); return Result(True, f"Volume set to {level}%")
        if k == T.CHANGE_VOLUME: level = self.volume.change(action.params["delta"]); return Result(True, f"Volume set to {level}%")
        if k in {T.MUTE, T.UNMUTE}: self.volume.mute(k == T.MUTE); return Result(True, "Muted" if k == T.MUTE else "Unmuted")
        operations = {T.COPY_PATH: self.files.copy, T.MOVE_PATH: self.files.move, T.RENAME_PATH: self.files.rename}
        if k in operations: path = operations[k](action.target, action.params["destination"]); return Result(True, f"Completed: {path}")
        if k == T.DELETE_PATH: self.files.delete(action.target); return Result(True, "Moved item to Recycle Bin")
        raise NotImplementedError(k)

    @property
    def browser_state(self):
        return None if self._browser is None else self._browser.state

    def close(self):
        with self._execution_lock:
            if self._browser is not None:
                self._browser.close()
                self._browser = None
