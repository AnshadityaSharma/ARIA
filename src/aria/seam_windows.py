"""Read-only monitor/preferences queries and styles for ARIA-owned windows."""
import ctypes
from ctypes import wintypes
import os

from aria.seam_presentation import WorkArea


class MonitorInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                ("work", wintypes.RECT), ("flags", wintypes.DWORD)]


class HighContrast(ctypes.Structure):
    _fields_ = [("size", wintypes.UINT), ("flags", wintypes.DWORD),
                ("scheme", wintypes.LPWSTR)]


class WindowsSurface:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Native Seam placement requires Windows")
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        signatures = {
            "GetAncestor": ([wintypes.HWND, wintypes.UINT], wintypes.HWND),
            "GetForegroundWindow": ([], wintypes.HWND),
            "MonitorFromWindow": ([wintypes.HWND, wintypes.DWORD], wintypes.HANDLE),
            "GetMonitorInfoW": ([wintypes.HANDLE, ctypes.POINTER(MonitorInfo)], wintypes.BOOL),
            "GetDpiForWindow": ([wintypes.HWND], wintypes.UINT),
            "GetWindowLongPtrW": ([wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t),
            "SetWindowLongPtrW": ([wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t),
            "ShowWindow": ([wintypes.HWND, ctypes.c_int], wintypes.BOOL),
            "SystemParametersInfoW": ([wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result

    def hwnd(self, window):
        return self.api.GetAncestor(window.winfo_id(), 2) or window.winfo_id()

    def work_area(self, hwnd=None):
        hwnd = hwnd or self.api.GetForegroundWindow()
        monitor = self.api.MonitorFromWindow(hwnd, 2)
        info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
        if not self.api.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        dpi = self.api.GetDpiForWindow(hwnd) or 96
        # GetDpiForMonitor is optional and obeys the host's DPI-awareness policy.
        try:
            shcore = ctypes.WinDLL("shcore")
            function = shcore.GetDpiForMonitor
            function.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT)]
            function.restype = ctypes.c_long
            x, y = wintypes.UINT(), wintypes.UINT()
            if function(monitor, 0, ctypes.byref(x), ctypes.byref(y)) == 0:
                dpi = x.value or dpi
        except (OSError, AttributeError):
            pass
        r = info.work
        return WorkArea(r.left, r.top, r.right, r.bottom, dpi)

    def preferences(self):
        contrast = HighContrast(size=ctypes.sizeof(HighContrast))
        animations = wintypes.BOOL(True)
        contrast_ok = self.api.SystemParametersInfoW(0x42, contrast.size, ctypes.byref(contrast), 0)
        animation_ok = self.api.SystemParametersInfoW(0x1042, 0, ctypes.byref(animations), 0)
        return bool(contrast_ok and contrast.flags & 1), bool(animation_ok and not animations.value)

    def style(self, window, interactive=False):
        hwnd = self.hwnd(window)
        style = self.api.GetWindowLongPtrW(hwnd, -20) | 0x80  # tool window, no taskbar entry
        style = style & ~0x08000000 if interactive else style | 0x08000000
        ctypes.set_last_error(0)
        previous = self.api.SetWindowLongPtrW(hwnd, -20, style)
        if previous == 0 and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
    def show(self, window, interactive=False):
        self.style(window, interactive)
        window.deiconify()
        # Tk can rebuild extended styles when mapping or resizing its wrapper.
        self.style(window, interactive)
        hwnd = self.hwnd(window)
        self.api.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE


def enable_standalone_dpi():
    """Only the standalone synthetic demo opts its UI thread into per-monitor DPI."""
    if os.name == "nt":
        api = ctypes.WinDLL("user32", use_last_error=True)
        if hasattr(api, "SetThreadDpiAwarenessContext"):
            api.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            api.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            return bool(api.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4)))
    return False
