from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from aria.core import Rect
from aria.parser import ClarificationRequired

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.SetFocus.argtypes = [wintypes.HWND]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.IsHungAppWindow.argtypes = [wintypes.HWND]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class Placement(StrEnum):
    NORMAL = "normal"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"


@dataclass(frozen=True, slots=True)
class WindowIdentity:
    handle: int
    pid: int
    process_created: int


@dataclass(frozen=True, slots=True)
class Window:
    handle: int
    title: str
    rect: Rect
    pid: int
    identity: WindowIdentity | None = None
    executable: str | None = None
    application_id: str | None = None
    placement: Placement = Placement.NORMAL


def _normalized(value: str) -> str:
    return " ".join(value.casefold().removesuffix(".exe").split())


class WindowManager:
    verification_timeout = 1.5

    def rect(self, handle: int) -> Rect:
        value = wintypes.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(value)):
            raise OSError(ctypes.get_last_error(), "GetWindowRect failed")
        return Rect(value.left, value.top, value.right - value.left, value.bottom - value.top)

    def title(self, handle: int) -> str:
        length = user32.GetWindowTextLengthW(handle)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, buf, len(buf))
        return buf.value

    def exists(self, handle: int | None) -> bool:
        return bool(handle and user32.IsWindow(handle))

    def active(self) -> int:
        handle = user32.GetForegroundWindow()
        if not handle: raise LookupError("No active window")
        return int(handle)

    def _process(self, pid: int) -> tuple[int | None, str | None, str | None]:
        process = kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return None, None, None
        try:
            created = wintypes.FILETIME(); exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME(); user = wintypes.FILETIME()
            created_value = None
            if kernel32.GetProcessTimes(process, ctypes.byref(created), ctypes.byref(exited),
                                        ctypes.byref(kernel), ctypes.byref(user)):
                created_value = (created.dwHighDateTime << 32) | created.dwLowDateTime
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            executable = buffer.value if kernel32.QueryFullProcessImageNameW(
                process, 0, buffer, ctypes.byref(size)) else None
            application_id = None
            get_app_id = getattr(kernel32, "GetApplicationUserModelId", None)
            if get_app_id is not None:
                length = wintypes.UINT(0)
                get_app_id(process, ctypes.byref(length), None)
                if length.value:
                    app_buffer = ctypes.create_unicode_buffer(length.value)
                    if get_app_id(process, ctypes.byref(length), app_buffer) == 0:
                        application_id = app_buffer.value or None
            return created_value, executable, application_id
        finally:
            kernel32.CloseHandle(process)

    def placement(self, handle: int) -> Placement:
        if user32.IsIconic(handle):
            return Placement.MINIMIZED
        if user32.IsZoomed(handle):
            return Placement.MAXIMIZED
        return Placement.NORMAL

    def snapshot(self, handle: int) -> Window:
        if not self.exists(handle):
            raise LookupError("The target window is no longer available")
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        created, executable, application_id = self._process(pid.value)
        identity = WindowIdentity(int(handle), pid.value, created) if created is not None else None
        return Window(int(handle), self.title(handle), self.rect(handle), pid.value, identity,
                      executable, application_id, self.placement(handle))

    def windows(self) -> list[Window]:
        found: list[Window] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(handle: int, _param: int) -> bool:
            if user32.IsWindowVisible(handle) and self.title(handle):
                try:
                    found.append(self.snapshot(handle))
                except (OSError, LookupError):
                    pass  # Window disappeared during enumeration.
            return True
        callback = callback_type(visit)
        user32.EnumWindows(callback, 0)
        return found

    @staticmethod
    def _unique(matches: list[Window], query: str) -> Window:
        # EnumWindows can expose the same HWND twice across a desktop transition.
        # One stable identity is still one target; distinct identities remain ambiguous.
        matches = list({item.identity or (item.handle, item.pid): item for item in matches}.values())
        if not matches:
            raise ClarificationRequired(f"No visible window matches {query!r}")
        if len(matches) != 1:
            descriptions = ", ".join(
                f"{item.title} (HWND {item.handle}, PID {item.pid})" for item in matches[:5])
            raise ClarificationRequired(f"Window target {query!r} is ambiguous: {descriptions}")
        result = matches[0]
        if result.identity is None:
            raise LookupError("Window identity cannot be established reliably")
        return result

    def resolve(self, query: str) -> Window:
        key = _normalized(query)
        if not key:
            raise LookupError("Window target is empty")
        items = self.windows()
        exact_title = [item for item in items if _normalized(item.title) == key]
        if exact_title:
            return self._unique(exact_title, query)
        exact_identity = [item for item in items if any(
            value and _normalized(value) == key for value in (
                Path(item.executable).stem if item.executable else None, item.application_id))]
        if exact_identity:
            return self._unique(exact_identity, query)
        partial = [item for item in items if any(
            value and key in _normalized(value) for value in (
                item.title, Path(item.executable).stem if item.executable else None, item.application_id))]
        return self._unique(partial, query)

    def find(self, query: str) -> int:
        return self.resolve(query).handle

    def recheck(self, target: Window | WindowIdentity) -> Window:
        identity = target.identity if isinstance(target, Window) else target
        if identity is None:
            raise LookupError("Window identity cannot be established reliably")
        current = self.snapshot(identity.handle)
        if current.identity != identity:
            raise LookupError("Window identity changed before execution")
        return current

    def active_window(self) -> Window:
        current = self.snapshot(self.active())
        if current.identity is None:
            raise LookupError("Foreground window identity cannot be established reliably")
        return current

    def work_area(self, target: int | Window) -> Rect:
        handle = self.recheck(target).handle if isinstance(target, Window) else target
        monitor = user32.MonitorFromWindow(handle, 2)
        class Info(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        info = Info(); info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)): raise OSError("GetMonitorInfo failed")
        r = info.rcWork
        return Rect(r.left, r.top, r.right-r.left, r.bottom-r.top)

    def focus(self, target: int | Window) -> Window | None:
        expected = self.recheck(target) if isinstance(target, Window) else None
        handle = expected.handle if expected else target
        foreground = user32.GetForegroundWindow()
        current_thread = kernel32.GetCurrentThreadId()
        foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        target_thread = user32.GetWindowThreadProcessId(handle, None)
        attached = []
        try:
            for thread in {foreground_thread, target_thread} - {0, current_thread}:
                if user32.AttachThreadInput(current_thread, thread, True):
                    attached.append(thread)
            user32.ShowWindow(handle, 9)
            user32.BringWindowToTop(handle)
            user32.SetForegroundWindow(handle)
            user32.SetFocus(handle)
        finally:
            for thread in reversed(attached):
                user32.AttachThreadInput(current_thread, thread, False)
        deadline = time.monotonic() + self.verification_timeout
        while time.monotonic() < deadline:
            if self.active() == handle:
                current = self.snapshot(handle)
                if expected is not None and current.identity != expected.identity:
                    raise LookupError("Window identity changed while focusing")
                return current
            time.sleep(.01)
        raise OSError("Windows did not focus the requested window")

    def show(self, target: int | Window, mode: str) -> Window | None:
        expected = self.recheck(target) if isinstance(target, Window) else None
        handle = expected.handle if expected else target
        user32.ShowWindow(handle, {"minimize": 6, "maximize": 3, "restore": 9}[mode])
        wanted = {
            "minimize": Placement.MINIMIZED,
            "maximize": Placement.MAXIMIZED,
            "restore": Placement.NORMAL,
        }[mode]
        deadline = time.monotonic() + self.verification_timeout
        while time.monotonic() < deadline:
            current = self.snapshot(handle)
            if expected is not None and current.identity != expected.identity:
                raise LookupError("Window identity changed while changing placement")
            if current.placement == wanted:
                return current
            time.sleep(.01)
        raise OSError(f"Windows did not {mode} the requested window")

    def place(self, target: int | Window, rect: Rect) -> Rect | Window:
        expected = self.recheck(target) if isinstance(target, Window) else None
        handle = expected.handle if expected else target
        # Let the target apply its own sizing rules. Modern apps can return
        # contradictory WM_GETMINMAXINFO limits during a layout transition.
        # Read back the committed rectangle and report constraints to the caller.
        if not user32.SetWindowPos(handle, 0, rect.x, rect.y, rect.width, rect.height, 0x4014):
            raise OSError(ctypes.get_last_error(), "SetWindowPos failed")
        deadline = time.monotonic() + 1
        previous = None
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            actual = self.rect(handle)
            if actual.width <= 0 or actual.height <= 0:
                raise OSError("Window returned invalid geometry after the operation")
            complete = actual == rect
            if actual != previous:
                previous, stable_since = actual, time.monotonic()
            elif time.monotonic() - stable_since >= .2:
                complete = True
            if complete:
                if user32.IsHungAppWindow(handle):
                    raise OSError("Target window is not responding")
                if expected is None:
                    return actual
                current = self.snapshot(handle)
                if current.identity != expected.identity:
                    raise LookupError("Window identity changed while moving or resizing")
                return current
            time.sleep(.01)
        raise OSError("Timed out verifying window geometry")

    @staticmethod
    def _app_matches(window: Window, application) -> bool:
        app_id = _normalized(getattr(application, "app_id", ""))
        name = _normalized(getattr(application, "name", ""))
        executable = _normalized(Path(window.executable).stem) if window.executable else ""
        return bool((app_id and window.application_id and _normalized(window.application_id) == app_id)
                    or (name and (_normalized(window.title) == name or executable == name)))

    def wait_for_application(self, application, existing: set[WindowIdentity],
                             previous_foreground: WindowIdentity | None, timeout: float = 8) -> Window:
        end = time.monotonic() + timeout
        ambiguity = False
        while time.monotonic() < end:
            items = [item for item in self.windows() if item.identity is not None]
            new = [item for item in items if item.identity not in existing]
            strong_new = [item for item in new if self._app_matches(item, application)]
            if len(strong_new) == 1:
                return strong_new[0]
            if len(strong_new) > 1:
                ambiguity = True
            elif len(new) == 1:
                return new[0]
            elif len(new) > 1:
                ambiguity = True
            try:
                active = self.active_window()
                if active.identity != previous_foreground and self._app_matches(active, application):
                    matches = [item for item in items if self._app_matches(item, application)]
                    if len(matches) == 1:
                        return active
                    ambiguity = True
            except (LookupError, OSError):
                pass
            time.sleep(.1)
        if ambiguity:
            raise LookupError(f"Application {application.name!r} opened ambiguously; no window was selected")
        raise LookupError(f"Application {application.name!r} did not expose a verifiable window")

    def wait_for(self, title: str, existing: set[int], timeout: float = 8) -> int:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            candidates = [item for item in self.windows()
                          if item.handle not in existing and _normalized(title) in _normalized(item.title)]
            if len(candidates) == 1:
                return candidates[0].handle
            if len(candidates) > 1:
                raise LookupError(f"Application window {title!r} is ambiguous")
            time.sleep(.1)
        return self.find(title)


def target_rect(current: Rect, work: Rect, *, scale: float | None = None, ratio: float | None = None, position: str | None = None, pixels: int = 50) -> Rect:
    width = max(160, round(work.width * ratio)) if ratio else max(160, round(current.width * (scale or 1)))
    height = max(120, round(work.height * ratio)) if ratio else max(120, round(current.height * (scale or 1)))
    x, y = current.x, current.y
    step = pixels
    positions = {
        "top_left": (work.x, work.y), "top_right": (work.x+work.width-width, work.y),
        "bottom_left": (work.x, work.y+work.height-height), "bottom_right": (work.x+work.width-width, work.y+work.height-height),
        "center": (work.x+(work.width-width)//2, work.y+(work.height-height)//2), "top": (current.x, work.y), "bottom": (current.x, work.y+work.height-height),
        "right": (min(current.x+step, work.x+work.width-width), current.y), "left": (max(current.x-step, work.x), current.y),
        "up": (current.x, max(current.y-step, work.y)), "down": (current.x, min(current.y+step, work.y+work.height-height)),
    }
    if position: x, y = positions[position]
    return Rect(x, y, width, height)
