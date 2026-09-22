from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass

from aria.core import Rect

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


@dataclass(frozen=True, slots=True)
class Window:
    handle: int
    title: str
    rect: Rect
    pid: int


class WindowManager:
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
        return handle

    def windows(self) -> list[Window]:
        found: list[Window] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(handle: int, _param: int) -> bool:
            if user32.IsWindowVisible(handle) and (title := self.title(handle)):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
                found.append(Window(handle, title, self.rect(handle), pid.value))
            return True
        callback = callback_type(visit)
        user32.EnumWindows(callback, 0)
        return found

    def find(self, query: str) -> int:
        key = query.casefold().removesuffix(".exe")
        matches = [w for w in self.windows() if key in w.title.casefold()]
        if not matches: raise LookupError(f"No visible window matches {query!r}")
        return matches[0].handle

    def work_area(self, handle: int) -> Rect:
        monitor = user32.MonitorFromWindow(handle, 2)
        class Info(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        info = Info(); info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)): raise OSError("GetMonitorInfo failed")
        r = info.rcWork
        return Rect(r.left, r.top, r.right-r.left, r.bottom-r.top)

    def focus(self, handle: int) -> None:
        user32.ShowWindow(handle, 9)
        if not user32.SetForegroundWindow(handle): raise OSError("Windows refused to focus the window")

    def show(self, handle: int, mode: str) -> None:
        user32.ShowWindow(handle, {"minimize": 6, "maximize": 3, "restore": 9}[mode])

    def place(self, handle: int, rect: Rect) -> Rect:
        if not user32.SetWindowPos(handle, 0, rect.x, rect.y, rect.width, rect.height, 0x0014):
            raise OSError(ctypes.get_last_error(), "SetWindowPos failed")
        actual = self.rect(handle)
        if abs(actual.x-rect.x) > 2 or abs(actual.width-rect.width) > 2:
            raise OSError("Window did not reach the requested geometry")
        return actual

    def wait_for(self, title: str, existing: set[int], timeout: float = 8) -> int:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            candidates = [w for w in self.windows() if w.handle not in existing and title.casefold() in w.title.casefold()]
            if candidates: return candidates[0].handle
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
