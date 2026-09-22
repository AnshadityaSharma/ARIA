import os
import subprocess
import time

import pytest

from aria.core import Rect
from aria.windows import WindowManager

pytestmark = pytest.mark.windows_integration


@pytest.mark.skipif(os.environ.get("ARIA_WINDOWS_INTEGRATION") != "1", reason="set ARIA_WINDOWS_INTEGRATION=1")
def test_move_disposable_notepad_window():
    process = subprocess.Popen(["notepad.exe"])
    manager = WindowManager()
    try:
        handle = manager.wait_for("Notepad", set(), 10); original = manager.rect(handle)
        requested = Rect(original.x + 20, original.y + 20, max(300, original.width), max(200, original.height))
        assert manager.place(handle, requested) == requested
    finally:
        process.terminate()
