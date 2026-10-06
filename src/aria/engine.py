from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass
from pathlib import Path

from aria.core import Action, ActionType as T, Rect, Result, Verification, WindowState, RISK
from aria.desktop import Applications, Files, Volume, screenshot
from aria.intent import Interpreter
from aria.windows import Placement, Window, WindowManager, target_rect
from aria.permissions import ConfirmationRequired, PermissionEngine, PermissionDenied, Decision
from aria.parser import ClarificationRequired


@dataclass(frozen=True, slots=True)
class TargetBinding:
    action: Action
    identity: object


class ExecutionFailed(RuntimeError):
    def __init__(self, result: Result):
        self.result = result
        super().__init__(result.message)


BROWSER_ACTIONS = frozenset({T.OPEN_BROWSER, T.OPEN_WEBSITE, T.NAVIGATE_BROWSER, T.SEARCH_WEB,
    T.SEARCH_YOUTUBE, T.PLAY_YOUTUBE, T.TYPE_IN_BROWSER, T.CLICK_BROWSER_ELEMENT,
    T.SUBMIT_BROWSER, T.DOWNLOAD_FILE})
FILE_SOURCE_ACTIONS = frozenset({T.DELETE_PATH, T.MOVE_PATH, T.RENAME_PATH, T.COPY_PATH})
DISPATCH_ACTIONS = BROWSER_ACTIONS | frozenset({T.SHUTDOWN, T.OPEN_APPLICATION, T.FOCUS_WINDOW,
    T.MINIMIZE_WINDOW, T.MAXIMIZE_WINDOW, T.RESTORE_WINDOW, T.RESIZE_WINDOW, T.MOVE_WINDOW,
    T.CREATE_FOLDER, T.OPEN_PATH, T.TAKE_SCREENSHOT, T.SET_VOLUME, T.CHANGE_VOLUME,
    T.MUTE, T.UNMUTE}) | FILE_SOURCE_ACTIONS
assert set(DISPATCH_ACTIONS) == set(T) == set(RISK)


class Engine:
    def __init__(self, windows=None, applications=None, files=None, volume=None, permissions=None, shutdown=None,
                 browser_factory=None, interpreter=None, *, clock=time.monotonic,
                 reference_ttl_seconds=300):
        self.windows = windows or WindowManager(); self.applications = applications or Applications()
        self.files = files or Files(); self.volume = volume or Volume(); self.state = WindowState()
        self.permissions = permissions or PermissionEngine()
        self._execution_lock = threading.RLock()
        self._pending_binding = None
        self.activation_window = None
        self._browser = None
        self._browser_factory = browser_factory
        self.interpreter = interpreter or Interpreter()
        self.clock = clock
        self.reference_ttl_seconds = reference_ttl_seconds
        if shutdown is None:
            from aria.desktop import shutdown_computer
            shutdown = shutdown_computer
        self._shutdown = shutdown

    def run_text(self, text: str) -> Result:
        self.cancel()
        captured = self.activation_window is None
        if captured:
            try:
                current = self.windows.active_window() if hasattr(self.windows, "active_window") else self.windows.active()
                self.activation_window = current.identity if isinstance(current, Window) else current
            except (LookupError, OSError, AttributeError):
                pass
        try:
            started = time.perf_counter(); action = self.interpret(text)
            result = self.execute(action)
            logging.getLogger("aria").info("action=%s ok=%s elapsed_ms=%.3f", action.kind, result.ok, (time.perf_counter()-started)*1000)
            return result
        finally:
            if captured: self.activation_window = None

    def interpret(self, text, *, on_event=None, original_text=None):
        return self.interpreter.interpret(text, on_event=on_event, original_text=original_text)

    def cancel_intent(self):
        self.interpreter.close()

    def _handle(self, target: str | None):
        if target == "foreground" or target is None:
            captured = self.activation_window
            if isinstance(captured, Window): return self.windows.recheck(captured)
            if captured is not None and not isinstance(captured, int): return self.windows.recheck(captured)
            handle = captured if captured is not None else self.windows.active()
            return self.windows.snapshot(handle) if hasattr(self.windows, "snapshot") else handle
        if target in {"tracked", "it", "that"}:
            if self.state.handle is None or not self.state.verified:
                raise ClarificationRequired("There is no recent verified window; name one or say 'this window'.")
            if (self.state.updated_at is not None
                    and self.clock() - self.state.updated_at > self.reference_ttl_seconds):
                self.state = WindowState()
                raise ClarificationRequired("The recent-window reference expired; name the window again.")
            if self.state.identity is not None and hasattr(self.windows, "recheck"):
                return self.windows.recheck(self.state.identity)
            if self.windows.exists(self.state.handle): return self.state.handle
            self.state = WindowState()
            raise ClarificationRequired("The tracked window is unavailable; name a window or say 'this window'.")
        return self.windows.resolve(target) if hasattr(self.windows, "resolve") else self.windows.find(target)

    def _track(self, target, action: T | None = None) -> Rect:
        current = target if isinstance(target, Window) else None
        if current is None and hasattr(self.windows, "snapshot"):
            current = self.windows.snapshot(target)
        if current is not None:
            geometry = (self.state.geometry if current.placement == Placement.MINIMIZED
                        and self.state.handle == current.handle and self.state.geometry else current.rect)
            self.state.update(current.handle, current.title, geometry, action, identity=current.identity,
                              executable=current.executable, application_id=current.application_id,
                              placement=current.placement, now=self.clock(), verified=current.identity is not None)
            return geometry
        rect = self.windows.rect(target)
        self.state.update(target, self.windows.title(target), rect, action,
                          now=self.clock(), verified=False)
        return rect

    def cancel(self, token=None, reason="cancelled"):
        with self._execution_lock:
            self.permissions.cancel(token, reason)
            self._pending_binding = None

    def _prepare(self, action):
        if type(action) is not Action:
            raise PermissionDenied("Unsupported or malformed action")
        try:
            action.validate()
            if action.kind not in RISK:
                raise ValueError("Unsupported action")
        except (ValueError, TypeError, KeyError) as exc:
            raise PermissionDenied("Unsupported or malformed action") from exc
        if action.kind in {T.OPEN_WEBSITE, T.NAVIGATE_BROWSER}:
            from aria.browser import normalize_url
            action = Action(action.kind, normalize_url(action.target), dict(action.params)).validate()
        if action.kind == T.OPEN_PATH:
            path = self.files.resolve(action.target)
            if not path.exists():
                raise FileNotFoundError(path)
            action = Action(action.kind, str(path), dict(action.params)).validate()
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
    def _path_identity(path):
        stat = Path(path).stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

    def _browser_adapter(self):
        if self._browser is None:
            if self._browser_factory is None:
                from aria.browser import BrowserManager
                self._browser = BrowserManager(files=self.files)
            else:
                self._browser = self._browser_factory()
        return self._browser

    def _target_identity(self, action):
        k = action.kind
        if k in FILE_SOURCE_ACTIONS:
            source = self._path_identity(action.target)
            if k == T.DELETE_PATH:
                return (source,)
            destination = Path(action.params["destination"])
            if k == T.RENAME_PATH:
                destination = Path(action.target).with_name(action.params["destination"])
            return (source, str(destination), not destination.exists())
        if k == T.CREATE_FOLDER:
            parent = Path(action.target)
            destination = parent / action.params["name"]
            return (self._path_identity(parent), str(destination), not destination.exists())
        if k == T.TAKE_SCREENSHOT:
            destination = Path(action.target)
            return (self._path_identity(destination.parent), str(destination), not destination.exists())
        if k in {T.CLICK_BROWSER_ELEMENT, T.SUBMIT_BROWSER, T.DOWNLOAD_FILE}:
            browser = self._browser_adapter()
            if not hasattr(browser, "capture_target"):
                raise PermissionDenied("Browser target cannot be bound for confirmation")
            return browser.capture_target(action)
        if k == T.SHUTDOWN:
            return ("local-computer",)
        raise PermissionDenied("This action has no reliable confirmation target binding")

    def _recheck_binding(self, binding):
        action = binding.action
        if action.kind in {T.CLICK_BROWSER_ELEMENT, T.SUBMIT_BROWSER, T.DOWNLOAD_FILE}:
            browser = self._browser_adapter()
            if not hasattr(browser, "same_target") or not browser.same_target(action, binding.identity):
                raise PermissionDenied("Target changed since confirmation was requested; repeat the command")
        elif self._target_identity(action) != binding.identity:
            raise PermissionDenied("Target changed since confirmation was requested; repeat the command")

    def execute(self, action: Action, *, on_event=None) -> Result:
        event = on_event or (lambda name: None)
        with self._execution_lock:
            self.cancel()
            event("validation_start")
            action = self._prepare(action)
            event("validation_complete")
            event("risk_start")
            decision = self.permissions.evaluate(action)
            event("risk_decision")
            if decision == Decision.CONFIRM:
                try:
                    identity = self._target_identity(action)
                except (OSError, LookupError, ValueError, AttributeError) as exc:
                    raise PermissionDenied("Target cannot be bound for confirmation") from exc
                if identity is None:
                    raise PermissionDenied("Target cannot be bound for confirmation")
                self._pending_binding = TargetBinding(action, identity)
                detail = None
                if action.kind in {T.CLICK_BROWSER_ELEMENT, T.SUBMIT_BROWSER, T.DOWNLOAD_FILE}:
                    detail = f"Page: {identity.url}\nRole: {'link' if action.kind == T.DOWNLOAD_FILE else action.params.get('role', 'button')}"
                raise ConfirmationRequired(self.permissions.request(action, target_detail=detail))
            if decision != Decision.ALLOW:
                raise PermissionDenied("Action denied")
            return self.__dispatch(action, event)

    def confirm(self, token: str, *, on_event=None) -> Result:
        with self._execution_lock:
            action = self.permissions.consume(token)
            binding = self._pending_binding
            self._pending_binding = None
            if binding is None or action != binding.action:
                raise PermissionDenied("Confirmation target is no longer available")
            event = on_event or (lambda name: None)
            event("validation_start")
            prepared = self._prepare(action)
            if prepared != action:
                raise PermissionDenied("Prepared action changed since confirmation was requested")
            event("validation_complete")
            event("risk_start")
            if self.permissions.evaluate(action) != Decision.CONFIRM:
                raise PermissionDenied("Confirmation policy changed")
            event("risk_decision")
            event("target_recheck_start")
            try:
                self._recheck_binding(binding)
            except (OSError, LookupError, ValueError, AttributeError) as exc:
                raise PermissionDenied("Target changed since confirmation was requested; repeat the command") from exc
            event("target_recheck_complete")
            return self.__dispatch(action, event, binding)

    def __dispatch(self, action, event, binding=None):
        event("execution_start")
        event("action_start")
        started = time.perf_counter()
        executed = False
        try:
            result = self.__perform(action, event, binding)
            executed = True
            event("action_complete")
            event("execution_complete")
            event("verification_start")
            if type(result) is not Result:
                event("verification_failed")
                raise ExecutionFailed(Result(False, "Executor returned an invalid result", verification=Verification.FAILED))
            if not result.ok or result.verification == Verification.FAILED:
                event("verification_failed")
                raise ExecutionFailed(result)
            event("verification_complete")
            logging.getLogger("aria").info("action=%s success=true elapsed_ms=%.3f", action.kind, (time.perf_counter()-started)*1000)
            return result
        except Exception:
            if not executed:
                event("execution_failed")
            logging.getLogger("aria").exception("action=%s execution_failed", action.kind)
            raise

    def __perform(self, action: Action, event, binding=None) -> Result:
        k = action.kind
        if k in BROWSER_ACTIONS:
            browser = self._browser_adapter()
            if binding is not None:
                if not hasattr(browser, "execute_bound"):
                    raise PermissionDenied("Browser cannot execute a bound target")
                return browser.execute_bound(action, binding.identity, event)
            return browser.execute(action, event)
        if k == T.SHUTDOWN:
            self._shutdown()
            return Result(True, "Windows shutdown requested")
        if k == T.OPEN_APPLICATION:
            event("target_resolution_start")
            before_windows = self.windows.windows()
            before_handles = {item.handle for item in before_windows}
            before_identities = {item.identity for item in before_windows if getattr(item, "identity", None)}
            previous_foreground = None
            if hasattr(self.windows, "active_window"):
                try: previous_foreground = self.windows.active_window().identity
                except (LookupError, OSError): pass
            application = self.applications.resolve(action.target) if hasattr(self.applications, "resolve") else None
            event("target_resolution_complete")
            event("target_recheck_start")
            if application is not None and hasattr(self.applications, "recheck"):
                application = self.applications.recheck(application)
            event("target_recheck_complete")
            launched = self.applications.launch(application or action.target)
            if application is not None and hasattr(self.windows, "wait_for_application"):
                current = self.windows.wait_for_application(launched or application, before_identities, previous_foreground)
                if current.identity is None:
                    raise LookupError("Launched application window identity is unreliable")
                geometry = self._track(current, k)
                return Result(True, f"Opened {application.name}",
                              {"handle": current.handle, "geometry": geometry, "app_id": application.app_id},
                              True, Verification.VERIFIED)
            handle = self.windows.wait_for(action.target, before_handles)
            geometry = self.windows.rect(handle)
            return Result(True, f"Opened {action.target}", {"handle": handle, "geometry": geometry},
                          True, Verification.UNVERIFIED)
        if k in {T.FOCUS_WINDOW, T.MINIMIZE_WINDOW, T.MAXIMIZE_WINDOW, T.RESTORE_WINDOW, T.RESIZE_WINDOW, T.MOVE_WINDOW}:
            event("target_resolution_start")
            target = self._handle(action.target)
            event("target_resolution_complete")
            event("target_recheck_start")
            if isinstance(target, Window):
                target = self.windows.recheck(target)
            event("target_recheck_complete")
            requested = None
            restored = False
            if k == T.FOCUS_WINDOW:
                observed = self.windows.focus(target)
            elif k in {T.MINIMIZE_WINDOW, T.MAXIMIZE_WINDOW, T.RESTORE_WINDOW}:
                observed = self.windows.show(target, k.value.split("_")[0].lower())
            else:
                if isinstance(target, Window) and target.placement != Placement.NORMAL:
                    target = self.windows.show(target, "restore")
                    restored = True
                current = target.rect if isinstance(target, Window) else self.windows.rect(target)
                work = self.windows.work_area(target)
                rect = target_rect(current, work, scale=action.params.get("scale"),
                                   ratio=action.params.get("screen_ratio"),
                                   position=action.params.get("position"),
                                   pixels=action.params.get("pixels", 50))
                requested = rect
                observed = self.windows.place(target, rect)
            stable = observed if isinstance(observed, Window) else target
            verified = isinstance(stable, Window) and stable.identity is not None
            if verified:
                geometry = self._track(stable, k)
            elif isinstance(observed, Rect):
                geometry = observed
            else:
                geometry = self.windows.rect(stable)
            constrained = requested is not None and any(abs(a-b)>2 for a,b in zip(
                (geometry.x,geometry.y,geometry.width,geometry.height),
                (requested.x,requested.y,requested.width,requested.height)))
            message = f"Windows/application constrained this request; actual rectangle is ({geometry.x}, {geometry.y}, {geometry.width}, {geometry.height})" if constrained else f"Completed {k}"
            return Result(True, message, {"geometry": geometry, "constrained": constrained,
                          "restored_before_operation": restored,
                          "placement": stable.placement if isinstance(stable, Window) else None},
                          verified, Verification.VERIFIED if verified else Verification.UNVERIFIED)
        if k == T.CREATE_FOLDER:
            path = self.files.create_folder(action.target, action.params["name"])
            verified = Path(path).is_dir()
            return Result(True, f"Created {path}" if verified else f"Folder creation was not verified: {path}",
                          observed=verified, verification=Verification.VERIFIED if verified else Verification.FAILED)
        if k == T.OPEN_PATH:
            event("target_recheck_start")
            path = self.files.resolve(action.target)
            before = self._path_identity(path)
            if self._path_identity(self.files.resolve(action.target)) != before:
                raise PermissionDenied("Path changed before execution")
            event("target_recheck_complete")
            opened = self.files.open(action.target)
            return Result(True, f"Windows accepted the open request for {opened}",
                          {"path": str(opened)}, True, Verification.UNVERIFIED)
        if k == T.TAKE_SCREENSHOT:
            path = screenshot(action.target)
            verified = Path(path).is_file()
            return Result(True, f"Saved screenshot to {path}" if verified else f"Screenshot output was not found: {path}",
                          observed=verified, verification=Verification.UNVERIFIED if verified else Verification.FAILED)
        if k == T.SET_VOLUME: level = self.volume.set(action.params["level"]); return Result(True, f"Volume set to {level}%")
        if k == T.CHANGE_VOLUME: level = self.volume.change(action.params["delta"]); return Result(True, f"Volume set to {level}%")
        if k in {T.MUTE, T.UNMUTE}: self.volume.mute(k == T.MUTE); return Result(True, "Muted" if k == T.MUTE else "Unmuted")
        operations = {T.COPY_PATH: self.files.copy, T.MOVE_PATH: self.files.move, T.RENAME_PATH: self.files.rename}
        if k in operations:
            path = operations[k](action.target, action.params["destination"])
            verified = Path(path).exists() and (k == T.COPY_PATH or not Path(action.target).exists())
            return Result(True, f"Completed: {path}" if verified else f"Output was not verified: {path}",
                          observed=verified, verification=(Verification.UNVERIFIED if k == T.COPY_PATH else Verification.VERIFIED)
                          if verified else Verification.FAILED)
        if k == T.DELETE_PATH:
            self.files.delete(action.target)
            verified = not Path(action.target).exists()
            return Result(True, "Source removed; Recycle Bin placement is unverified" if verified else "Delete was not verified on disk",
                          observed=verified, verification=Verification.UNVERIFIED if verified else Verification.FAILED)
        raise NotImplementedError(k)

    @property
    def browser_state(self):
        return None if self._browser is None else self._browser.state

    def close(self):
        self.cancel_intent()
        with self._execution_lock:
            if self._browser is not None:
                self._browser.close()
                self._browser = None
