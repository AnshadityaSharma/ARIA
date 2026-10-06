import pytest

from aria.core import Action, ActionType as T, Rect
from aria.engine import Engine
from aria.parser import ParseError, parse
from aria.desktop import Application
from aria.windows import Placement, Window, WindowIdentity, target_rect


def test_parser_demo_sequence():
    assert parse("open Camera").kind == T.OPEN_APPLICATION
    assert parse("make it one fifth of the screen").params == {"screen_ratio": .2}
    assert parse("move it to the top right").params == {"position": "top_right"}
    assert parse("make it 10% smaller").params == {"scale": .9}


@pytest.mark.parametrize("command,kind", [("maximize", T.MAXIMIZE_WINDOW), ("take a screenshot", T.TAKE_SCREENSHOT), ("mute", T.MUTE), ("set volume to 42%", T.SET_VOLUME)])
def test_other_commands(command, kind): assert parse(command).kind == kind


def test_ambiguous_text_is_rejected():
    with pytest.raises(ParseError): parse("do the thing")


def test_geometry_is_deterministic():
    current, work = Rect(100, 100, 1000, 800), Rect(0, 0, 1920, 1040)
    assert target_rect(current, work, scale=.9) == Rect(100, 100, 900, 720)
    assert target_rect(current, work, position="top_right") == Rect(920, 0, 1000, 800)
    assert target_rect(current, work, ratio=.2) == Rect(100, 100, 384, 208)


class FakeWindows:
    def __init__(self): self.value = Rect(100, 100, 1000, 800); self.placement = Placement.NORMAL
    def snapshot(self, handle):
        if handle != 7: raise LookupError("missing")
        return Window(7, "Demo", self.value, 70, WindowIdentity(7, 70, 700),
                      "demo.exe", "fixture.demo", self.placement)
    def windows(self): return [self.snapshot(7)]
    def wait_for(self, *_): return 7
    def wait_for_application(self, *_): return self.snapshot(7)
    def exists(self, handle): return handle == 7
    def active(self): return 7
    def active_window(self): return self.snapshot(7)
    def find(self, _): return 7
    def resolve(self, _): return self.snapshot(7)
    def recheck(self, target):
        identity = target.identity if isinstance(target, Window) else target
        if identity != self.snapshot(7).identity: raise LookupError("identity changed")
        return self.snapshot(7)
    def rect(self, _): return self.value
    def title(self, _): return "Demo"
    def work_area(self, _): return Rect(0, 0, 1920, 1040)
    def place(self, target, rect): self.recheck(target); self.value = rect; return self.snapshot(7)
    def focus(self, target): self.recheck(target); return self.snapshot(7)
    def show(self, target, mode):
        self.recheck(target)
        self.placement = {"minimize": Placement.MINIMIZED, "maximize": Placement.MAXIMIZED,
                          "restore": Placement.NORMAL}[mode]
        return self.snapshot(7)


class FakeApps:
    def resolve(self, name): return Application(name, f"fixture.{name.casefold()}")
    def recheck(self, application): return application
    def launch(self, application): return application


def test_minimal_state_tracks_each_successful_operation():
    windows = FakeWindows(); engine = Engine(windows=windows, applications=FakeApps())
    engine.execute(Action(T.OPEN_APPLICATION, "demo"))
    assert engine.state.handle == 7 and engine.state.geometry == Rect(100, 100, 1000, 800)
    engine.run_text("make it smaller")
    assert engine.state.geometry == Rect(100, 100, 900, 720)
    engine.run_text("move it to the right")
    assert engine.state.geometry == Rect(150, 100, 900, 720)


def test_extended_sequential_references_and_history():
    windows=FakeWindows(); engine=Engine(windows=windows,applications=FakeApps())
    engine.execute(Action(T.OPEN_APPLICATION,"demo")); engine.run_text("make it 20% smaller")
    assert engine.state.previous_geometry == Rect(100,100,1000,800)
    engine.run_text("move that 100 pixels left"); assert engine.state.geometry == Rect(0,100,800,640)
    engine.run_text("make this window half the size"); assert engine.state.geometry == Rect(0,100,400,320)


def test_missing_tracked_window_does_not_silently_change_target():
    windows=FakeWindows(); windows.exists=lambda _handle: False
    with pytest.raises(LookupError,match="recent verified window"): Engine(windows=windows).run_text("make it smaller")


def test_application_constrained_geometry_is_tracked_and_reported():
    windows=FakeWindows()
    def constrained_place(handle, requested):
        windows.value=Rect(requested.x, requested.y, 800, 600)
        return windows.snapshot(7)
    windows.place=constrained_place
    engine=Engine(windows=windows, applications=FakeApps())
    engine.run_text("open demo")
    result=engine.run_text("make it one fifth of the screen")
    assert result.data["constrained"]
    assert engine.state.geometry == Rect(100,100,800,600)
    assert "constrained" in result.message
