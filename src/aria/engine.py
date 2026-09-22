from __future__ import annotations

import logging
import time

from aria.core import Action, ActionType as T, RISK, Rect, Result, Risk, WindowState
from aria.desktop import Applications, Files, Volume, screenshot
from aria.parser import parse
from aria.windows import WindowManager, target_rect


class ConfirmationRequired(RuntimeError): pass


class Engine:
    def __init__(self, windows=None, applications=None, files=None, volume=None):
        self.windows = windows or WindowManager(); self.applications = applications or Applications()
        self.files = files or Files(); self.volume = volume or Volume(); self.state = WindowState()

    def run_text(self, text: str, *, confirmed: bool = False) -> Result:
        started = time.perf_counter(); action = parse(text)
        result = self.execute(action, confirmed=confirmed)
        logging.getLogger("aria").info("action=%s ok=%s elapsed_ms=%.3f", action.kind, result.ok, (time.perf_counter()-started)*1000)
        return result

    def _handle(self, target: str | None) -> int:
        if target in {None, "tracked", "it", "this window"}:
            if self.windows.exists(self.state.handle): return self.state.handle
            return self.windows.active()
        return self.windows.find(target)

    def _track(self, handle: int) -> Rect:
        rect = self.windows.rect(handle); self.state.update(handle, self.windows.title(handle), rect); return rect

    def execute(self, action: Action, *, confirmed: bool = False) -> Result:
        action.validate(); risk = RISK[action.kind]
        if risk in {Risk.MEDIUM, Risk.HIGH} and not confirmed:
            raise ConfirmationRequired(f"{action.kind} requires explicit confirmation (risk: {risk})")
        k = action.kind
        if k == T.OPEN_APPLICATION:
            before = {w.handle for w in self.windows.windows()}; self.applications.launch(action.target)
            handle = self.windows.wait_for(action.target, before); self._track(handle)
            return Result(True, f"Opened {action.target}", {"handle": handle})
        if k in {T.FOCUS_WINDOW, T.MINIMIZE_WINDOW, T.MAXIMIZE_WINDOW, T.RESTORE_WINDOW, T.RESIZE_WINDOW, T.MOVE_WINDOW}:
            handle = self._handle(action.target)
            if k == T.FOCUS_WINDOW: self.windows.focus(handle)
            elif k in {T.MINIMIZE_WINDOW, T.MAXIMIZE_WINDOW, T.RESTORE_WINDOW}: self.windows.show(handle, k.value.split("_")[0].lower())
            else:
                current = self.windows.rect(handle); work = self.windows.work_area(handle)
                rect = target_rect(current, work, scale=action.params.get("scale"), ratio=action.params.get("screen_ratio"), position=action.params.get("position"))
                self.windows.place(handle, rect)
            geometry = self._track(handle)
            return Result(True, f"Completed {k}", {"geometry": geometry})
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
