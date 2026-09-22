import os
import subprocess
import time

import pytest

from aria.core import Rect
from aria.engine import Engine
from aria.windows import WindowManager

pytestmark = pytest.mark.windows_integration


@pytest.mark.skipif(os.environ.get("ARIA_WINDOWS_INTEGRATION") != "1", reason="set ARIA_WINDOWS_INTEGRATION=1")
def test_move_disposable_notepad_window():
    process = subprocess.Popen(["notepad.exe"])
    manager = WindowManager()
    try:
        handle = manager.wait_for("Notepad", set(), 10); original = manager.rect(handle)
        engine=Engine(windows=manager); engine.state.update(handle,manager.title(handle),original)
        engine.run_text("make it 10% smaller"); smaller=engine.state.geometry
        assert smaller.width == round(original.width*.9)
        engine.run_text("move that 20 pixels right")
        assert engine.state.geometry.x == smaller.x+20
    finally:
        process.terminate()


@pytest.mark.skipif(os.environ.get("ARIA_WINDOWS_INTEGRATION") != "1", reason="set ARIA_WINDOWS_INTEGRATION=1")
def test_microphone_can_capture_local_audio():
    import sounddevice as sd
    devices=sd.query_devices()
    assert any(device["max_input_channels"]>0 for device in devices)
    audio=sd.rec(1600,samplerate=16000,channels=1,dtype="float32",blocking=True)
    assert audio.shape == (1600,1)
