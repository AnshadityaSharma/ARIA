"""Opt-in native tests affecting only the newly created ARIA windows."""
import os
import time
import tkinter as tk
import pytest

from aria.seam_ui import SeamWindow
from aria.seam_windows import enable_standalone_dpi
from aria.shard_presentation import DisplayState as S
from scripts.phase8_seam_demo import SyntheticSource

pytestmark = [pytest.mark.windows_integration,
              pytest.mark.skipif(os.environ.get("ARIA_SEAM_NATIVE") != "1", reason="set ARIA_SEAM_NATIVE=1 for own-window Seam tests")]


def pump(root, seconds=.1):
    until = time.perf_counter()+seconds
    while time.perf_counter() < until:
        root.update()
        time.sleep(.002)


@pytest.fixture(scope="module")
def native_root():
    enable_standalone_dpi()
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def surface(native_root):
    root = native_root
    ui = SeamWindow(root)
    yield root, ui, SyntheticSource(ui.adapter)
    ui.close()


def test_native_no_activation_placement_and_cleanup(surface):
    root, ui, source = surface
    foreground = ui.backend.api.GetForegroundWindow()
    source.show(S.VERIFIED)
    pump(root, .45)
    assert ui.compact.winfo_viewable()
    assert ui.fault is None
    assert ui.backend.api.GetForegroundWindow() == foreground
    x, y = ui.compact.winfo_rootx(), ui.compact.winfo_rooty()
    assert ui.area.left <= x < x+ui.compact.winfo_width() <= ui.area.right
    assert ui.area.top <= y < y+ui.compact.winfo_height() <= ui.area.bottom
    style = ui.backend.api.GetWindowLongPtrW(ui.backend.hwnd(ui.compact), -20)
    assert style & 0x08000000 and style & 0x80
    ui.close()
    assert not ui.jobs and not ui.adapter.submit_activity(None)
    ui.close()


def test_native_expansion_long_text_decision_is_only_an_intent(surface):
    root, ui, source = surface
    source.show(S.FINAL, long=True)
    pump(root)
    foreground = ui.backend.api.GetForegroundWindow()
    ui.expand(interactive=False)
    pump(root)
    assert ui.panel.winfo_viewable()
    assert len(ui.text.get("1.0", "end-1c")) > 1000
    assert ui.backend.api.GetForegroundWindow() == foreground
    ui.collapse()
    pump(root)
    assert not ui.panel.winfo_viewable()
    source.show(S.CONFIRMATION)
    pump(root)
    ui.confirm.invoke()
    assert ui.adapter.latest.state == S.CONFIRMATION
    assert list(ui.decision_intents)[-1][-1] == "confirm"


def test_native_hidden_idle_and_recovery(surface, monkeypatch):
    root, ui, source = surface
    pump(root, .4)
    paints = ui.paint_count
    pump(root, .2)
    assert ui.paint_count == paints
    ui.set_visible(False)
    source.show(S.LISTENING)
    pump(root)
    assert not ui.compact.winfo_viewable() and ui.paint_count == paints
    ui.set_visible(True)
    pump(root, .4)
    assert ui.compact.winfo_viewable()
    import aria.seam_ui as module
    draw = module.seam_image
    monkeypatch.setattr(module, "seam_image", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("simulated renderer loss")))
    source.show(S.FINAL)
    pump(root)
    assert ui.fault == "Seam renderer unavailable"
    assert not ui.compact.winfo_viewable()
    monkeypatch.setattr(module, "seam_image", draw)
    assert ui.recover()
    pump(root, .3)
    assert ui.fault is None and ui.compact.winfo_viewable()


def test_native_reduced_motion_high_contrast_and_keyboard_bindings(surface):
    root, ui, source = surface
    ui.reduced_motion = ui.high_contrast = True
    source.show(S.UNVERIFIED)
    pump(root)
    assert ui.frame.snapshot.state == S.UNVERIFIED
    assert ui.panel.winfo_viewable()
    assert ui.status.cget("fg") == "#ffffff"
    assert ui.close_button.winfo_rooty()+ui.close_button.winfo_height() <= ui.panel.winfo_rooty()+ui.panel.winfo_height()
    assert ui.canvas.bind("<Return>") and ui.canvas.bind("<Down>")
    assert ui.panel.bind("<Escape>")
    assert ui.text.cget("takefocus") == "1"
