"""A replaceable Windows RegisterHotKey adapter; no polling keyboard hooks."""
import ctypes
from ctypes import wintypes as W
import threading
import time

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32.RegisterHotKey.argtypes = [W.HWND, ctypes.c_int, W.UINT, W.UINT]
u32.RegisterHotKey.restype = W.BOOL
u32.UnregisterHotKey.argtypes = [W.HWND, ctypes.c_int]
u32.GetMessageW.argtypes = [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
u32.GetMessageW.restype = ctypes.c_int
u32.PostThreadMessageW.argtypes = [W.DWORD, W.UINT, W.WPARAM, W.LPARAM]
u32.GetForegroundWindow.restype = W.HWND
k32.GetCurrentThreadId.restype = W.DWORD


class GlobalHotkey:
    def __init__(self, callback, modifiers=0x0002, key=0x20):
        self.callback, self.modifiers, self.key = callback, modifiers, key
        self.ready = threading.Event()
        self.error = None
        self.thread_id = None
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="aria-hotkey", daemon=True)
        self.thread.start()
        if not self.ready.wait(3):
            raise RuntimeError("Global hotkey startup timed out")
        if self.error:
            raise self.error

    def _loop(self):
        self.thread_id = k32.GetCurrentThreadId()
        if not u32.RegisterHotKey(None, 1, self.modifiers | 0x4000, self.key):
            self.error = OSError("Ctrl+Space is already in use or unavailable")
            self.ready.set()
            return
        self.ready.set()
        try:
            message = W.MSG()
            while u32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:
                    self.callback(time.perf_counter(), u32.GetForegroundWindow())
        finally:
            u32.UnregisterHotKey(None, 1)

    def stop(self):
        if self.thread and self.thread.is_alive():
            u32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
            self.thread.join(timeout=3)
