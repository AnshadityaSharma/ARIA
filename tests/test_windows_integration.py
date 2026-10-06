import ctypes
import os
import subprocess
import sys
import time
import tkinter as tk
import uuid
from ctypes import wintypes
from pathlib import Path

import pytest

from aria.core import Action, ActionType as T, Verification
from aria.desktop import Applications
from aria.engine import Engine
from aria.windows import Placement, WindowManager

pytestmark = pytest.mark.windows_integration


@pytest.mark.skipif(os.environ.get("ARIA_WINDOWS_INTEGRATION") != "1", reason="set ARIA_WINDOWS_INTEGRATION=1")
def test_disposable_native_window_control_is_verified():
    root = tk.Tk()
    title = f"ARIA disposable {uuid.uuid4()}"
    root.title(title)
    root.geometry("800x600+100+100")
    root.update()
    manager = WindowManager()
    engine = Engine(windows=manager)
    try:
        original = manager.resolve(title)
        engine.state.update(original.handle, original.title, original.rect,
                            identity=original.identity, executable=original.executable,
                            application_id=original.application_id, placement=original.placement)

        focused = engine.execute(Action(T.FOCUS_WINDOW, "tracked"))
        assert focused.verification == Verification.VERIFIED
        assert manager.active_window().identity == original.identity

        for kind, wanted in ((T.MINIMIZE_WINDOW, Placement.MINIMIZED),
                             (T.MAXIMIZE_WINDOW, Placement.MAXIMIZED),
                             (T.RESTORE_WINDOW, Placement.NORMAL)):
            result = engine.execute(Action(kind, "tracked"))
            assert result.verification == Verification.VERIFIED
            assert manager.recheck(engine.state.identity).placement == wanted

        resized = engine.run_text("make it 10% smaller")
        assert resized.verification == Verification.VERIFIED
        assert abs(engine.state.geometry.width - round(original.rect.width * .9)) <= 2
        moved = engine.run_text("move that 20 pixels right")
        assert moved.verification == Verification.VERIFIED
        assert abs(engine.state.geometry.x - (resized.data["geometry"].x + 20)) <= 2

        engine.execute(Action(T.MAXIMIZE_WINDOW, "tracked"))
        top_right = engine.execute(Action(T.MOVE_WINDOW, "tracked", {"position": "top_right"}))
        work = manager.work_area(manager.recheck(engine.state.identity))
        assert top_right.verification == Verification.VERIFIED
        assert top_right.data["restored_before_operation"] is True
        assert abs(engine.state.geometry.x - (work.x + work.width - engine.state.geometry.width)) <= 2
        assert abs(engine.state.geometry.y - work.y) <= 2

        root.minsize(600, 450); root.update()
        constrained = engine.execute(Action(T.RESIZE_WINDOW, "tracked", {"scale": .1}))
        assert constrained.verification == Verification.VERIFIED
        assert constrained.data["constrained"] is True
    finally:
        root.destroy()
        engine.close()


@pytest.mark.skipif(os.environ.get("ARIA_WINDOWS_INTEGRATION") != "1", reason="set ARIA_WINDOWS_INTEGRATION=1")
def test_vanished_native_window_cannot_redirect_tracked_action():
    root = tk.Tk()
    title = f"ARIA stale {uuid.uuid4()}"
    root.title(title); root.update()
    manager = WindowManager(); target = manager.resolve(title)
    engine = Engine(windows=manager)
    engine.state.update(target.handle, target.title, target.rect, identity=target.identity,
                        executable=target.executable, application_id=target.application_id,
                        placement=target.placement)
    root.destroy()
    try:
        with pytest.raises(LookupError):
            engine.execute(Action(T.MOVE_WINDOW, "tracked", {"position": "right", "pixels": 10}))
    finally:
        engine.close()


def _create_shortcut(path: Path, target: Path, arguments: str) -> None:
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ARIA_TEST_SHORTCUT);"
        "$s.TargetPath=$env:ARIA_TEST_TARGET;$s.Arguments=$env:ARIA_TEST_ARGUMENTS;"
        "$s.WorkingDirectory=$env:ARIA_TEST_WORKING_DIRECTORY;$s.Save()"
    )
    environment = os.environ.copy()
    environment.update({"ARIA_TEST_SHORTCUT": str(path), "ARIA_TEST_TARGET": str(target),
                        "ARIA_TEST_ARGUMENTS": arguments,
                        "ARIA_TEST_WORKING_DIRECTORY": str(target.parent)})
    subprocess.run(["powershell", "-NoProfile", "-Command", script], env=environment,
                   check=True, timeout=10)


@pytest.mark.skipif(os.environ.get("ARIA_WINDOWS_INTEGRATION") != "1", reason="set ARIA_WINDOWS_INTEGRATION=1")
def test_generated_start_app_is_discovered_and_launches_verified_window():
    token = uuid.uuid4().hex
    application_name = f"ARIA fixture {token}"
    window_title = application_name
    programs = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs"
    shortcut = programs / f"{application_name}.lnk"
    fixture = Path(__file__).parent / "fixtures/window_app.py"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    _create_shortcut(shortcut, pythonw, f'"{fixture}" "{window_title}"')
    applications = Applications(); manager = WindowManager(); discovered = None
    launched_handle = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                discovered = applications.resolve(application_name)
                break
            except LookupError:
                time.sleep(.5)
        assert discovered is not None
        assert discovered.name == application_name

        engine = Engine(windows=manager, applications=applications)
        result = engine.execute(Action(T.OPEN_APPLICATION, application_name))
        launched_handle = result.data["handle"]
        assert result.verification == Verification.VERIFIED
        assert manager.recheck(engine.state.identity).title == window_title
    finally:
        if launched_handle and manager.exists(launched_handle):
            ctypes.windll.user32.PostMessageW(launched_handle, 0x0010, 0, 0)
        shortcut.unlink(missing_ok=True)


@pytest.mark.skipif(os.environ.get("ARIA_WINDOWS_INTEGRATION") != "1", reason="set ARIA_WINDOWS_INTEGRATION=1")
def test_second_monitor_geometry_when_available():
    if ctypes.windll.user32.GetSystemMetrics(80) < 2:
        pytest.skip("A second monitor is not connected")
    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    areas = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                       ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def visit(monitor, _dc, _rect, _param):
        info = MonitorInfo(); info.cbSize = ctypes.sizeof(info)
        assert ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        work = info.rcWork
        areas.append((work.left, work.top, work.right - work.left, work.bottom - work.top))
        return True
    callback = callback_type(visit)
    ctypes.windll.user32.EnumDisplayMonitors(0, None, callback, 0)
    assert len(areas) >= 2

    x, y, width, height = areas[1]
    root = tk.Tk(); title = f"ARIA second monitor {uuid.uuid4()}"
    root.title(title); root.geometry(f"640x480{x + 40:+d}{y + 40:+d}"); root.update()
    manager = WindowManager(); target = manager.resolve(title); engine = Engine(windows=manager)
    engine.state.update(target.handle, target.title, target.rect, identity=target.identity,
                        executable=target.executable, application_id=target.application_id,
                        placement=target.placement)
    try:
        result = engine.execute(Action(T.MOVE_WINDOW, "tracked", {"position": "top_right"}))
        assert result.verification == Verification.VERIFIED
        assert abs(engine.state.geometry.x - (x + width - engine.state.geometry.width)) <= 2
        assert abs(engine.state.geometry.y - y) <= 2
    finally:
        root.destroy(); engine.close()


@pytest.mark.skipif(os.environ.get("ARIA_WINDOWS_INTEGRATION") != "1", reason="set ARIA_WINDOWS_INTEGRATION=1")
def test_microphone_can_capture_local_audio():
    import sounddevice as sd
    devices=sd.query_devices()
    assert any(device["max_input_channels"]>0 for device in devices)
    audio=sd.rec(1600,samplerate=16000,channels=1,dtype="float32",blocking=True)
    assert audio.shape == (1600,1)
