"""Opt-in tests operating real Windows/Tk UI and disposable data."""
import ctypes
import os
import threading
import time
import tkinter as tk

import pytest

from aria.activation import ConfirmationPrompt
from aria.core import Action, ActionType as T
from aria.engine import Engine
from aria.hotkey import GlobalHotkey
from aria.permissions import ConfirmationRequired, PermissionEngine
from aria.ui import ConfirmationDialog
from aria.voice import Timeline

pytestmark = [
    pytest.mark.windows_integration,
    pytest.mark.skipif(os.environ.get("ARIA_DESKTOP_INTEGRATION") != "1",
                      reason="set ARIA_DESKTOP_INTEGRATION=1 to exercise hotkey and dialogs"),
]


def press_ctrl_space():
    u32 = ctypes.windll.user32
    u32.keybd_event(0x11, 0, 0, 0)
    u32.keybd_event(0x20, 0, 0, 0)
    u32.keybd_event(0x20, 0, 2, 0)
    u32.keybd_event(0x11, 0, 2, 0)


def test_real_global_hotkey_and_unregister():
    received = threading.Event()
    hotkey = GlobalHotkey(lambda timestamp, hwnd: received.set())
    hotkey.start()
    try:
        press_ctrl_space()
        assert received.wait(2), "Windows did not deliver Ctrl+Space"
    finally:
        hotkey.stop()
    assert not hotkey.thread.is_alive()
    # Registration released, so another owner can immediately acquire it.
    again = GlobalHotkey(lambda *_: None)
    again.start()
    again.stop()


def pending(engine, action):
    with pytest.raises(ConfirmationRequired) as exc:
        engine.execute(action)
    return exc.value.pending


def test_real_confirmation_cancel_then_recycle(tmp_path):
    target = tmp_path / "aria_disposable_confirmation.txt"
    target.write_text("ARIA integration test only")
    engine = Engine()
    root = tk.Tk()
    root.withdraw()
    try:
        action = Action(T.DELETE_PATH, str(target))
        request = pending(engine, action)
        prompt = ConfirmationPrompt(request, Timeline())
        dialog = ConfirmationDialog(root, prompt)
        root.update()
        assert str(target) in request.description
        dialog.cancel_button.invoke()
        engine.cancel(request.token)
        assert target.exists()
        assert prompt.answer == "cancelled"

        request = pending(engine, action)
        prompt = ConfirmationPrompt(request, Timeline())
        dialog = ConfirmationDialog(root, prompt)
        root.update()
        dialog.confirm_button.invoke()
        assert prompt.answer == "confirmed"
        engine.confirm(request.token)
        assert not target.exists()  # send2trash; item remains recoverable in Recycle Bin.
    finally:
        root.destroy()


def test_real_dialog_timeout_does_not_delete(tmp_path):
    target = tmp_path / "aria_timeout.txt"
    target.write_text("retain")
    engine = Engine(permissions=PermissionEngine(timeout=.1))
    root = tk.Tk()
    root.withdraw()
    try:
        request = pending(engine, Action(T.DELETE_PATH, str(target)))
        prompt = ConfirmationPrompt(request, Timeline())
        dialog = ConfirmationDialog(root, prompt)
        until = time.monotonic()+2
        while not prompt.done.is_set() and time.monotonic() < until:
            root.update()
            time.sleep(.01)
        assert prompt.answer == "timed_out"
        engine.cancel(request.token, reason="timed_out")
        assert target.exists()
    finally:
        root.destroy()
