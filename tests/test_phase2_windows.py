from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import json
import uuid

import pytest

from aria.core import Action, ActionType as T, Rect, Verification
from aria.desktop import Application, Applications, Files
from aria.engine import Engine
from aria.windows import Placement, Window, WindowIdentity, WindowManager


def window(handle=1, title="Demo", pid=10, created=100, *, executable="demo.exe",
           application_id=None, placement=Placement.NORMAL, rect=Rect(100, 100, 800, 600)):
    identity = WindowIdentity(handle, pid, created) if created is not None else None
    return Window(handle, title, rect, pid, identity, executable, application_id, placement)


def start_apps(monkeypatch, rows):
    result = SimpleNamespace(stdout=json.dumps(rows))
    monkeypatch.setattr("aria.desktop.subprocess.run", Mock(return_value=result))


def test_start_apps_preserves_duplicate_records_and_fails_ambiguity(monkeypatch):
    rows = [{"Name": "Tool", "AppID": "first"}, {"Name": "Tool", "AppID": "second"}]
    start_apps(monkeypatch, rows)
    applications = Applications()
    assert applications.discover() == [Application("Tool", "first"), Application("Tool", "second")]
    with pytest.raises(LookupError, match="ambiguous"):
        applications.resolve("tool")


def test_application_resolution_is_exact_then_unique_substring(monkeypatch):
    start_apps(monkeypatch, [
        {"Name": "Unique Editor", "AppID": "editor"},
        {"Name": "Unique Editor Preview", "AppID": "preview"},
        {"Name": "Calculator", "AppID": "calc"},
    ])
    applications = Applications()
    assert applications.resolve("unique editor").app_id == "editor"
    assert applications.resolve("calculator").app_id == "calc"
    with pytest.raises(LookupError, match="ambiguous"):
        applications.resolve("unique")
    with pytest.raises(LookupError, match="not found"):
        applications.resolve("missing")


def test_application_resolution_uses_discovery_derived_spacing_and_typo_keys(monkeypatch):
    start_apps(monkeypatch, [
        {"Name": "Note Pad", "AppID": "note"},
        {"Name": "Camera", "AppID": "camera"},
    ])
    applications = Applications()
    assert applications.resolve("notepad").app_id == "note"
    assert applications.resolve("camra").app_id == "camera"


def test_application_typo_resolution_fails_closed_on_tie(monkeypatch):
    start_apps(monkeypatch, [
        {"Name": "Camera", "AppID": "first"},
        {"Name": "Camira", "AppID": "second"},
    ])
    with pytest.raises(LookupError, match="ambiguous"):
        Applications().resolve("camra")


def test_generated_application_is_discovered_without_catalogue(monkeypatch):
    generated = f"ARIA fixture {uuid.uuid4()}"
    start_apps(monkeypatch, [{"Name": generated, "AppID": "generated.app"}])
    assert Applications().resolve(generated) == Application(generated, "generated.app")


def test_application_discovery_refreshes_after_short_cache_window(monkeypatch):
    clock = [10.0]
    rows = [[{"Name": "Existing", "AppID": "old"}],
            [{"Name": "Newly Registered", "AppID": "new"}]]
    calls = []
    def run(*_args, **_kwargs):
        calls.append(True)
        return SimpleNamespace(stdout=json.dumps(rows[min(len(calls) - 1, 1)]))
    monkeypatch.setattr("aria.desktop.subprocess.run", run)
    monkeypatch.setattr("aria.desktop.time.monotonic", lambda: clock[0])
    applications = Applications()
    assert applications.discover()[0].name == "Existing"
    assert applications.discover()[0].name == "Existing"
    clock[0] += applications.cache_seconds + .1
    assert applications.resolve("Newly Registered").app_id == "new"
    assert len(calls) == 2


def test_launch_uses_exact_discovered_app_id(monkeypatch):
    application = Application("Generated", "exact.app.id")
    applications = Applications()
    monkeypatch.setattr(applications, "discover", lambda: [application])
    launched = []
    monkeypatch.setattr("aria.desktop.os.startfile", launched.append)
    assert applications.launch(application) == application
    assert launched == ["shell:AppsFolder\\exact.app.id"]


def test_start_apps_recheck_fails_when_registration_changes(monkeypatch):
    applications = Applications()
    monkeypatch.setattr(applications, "discover", lambda: [Application("Tool", "changed")])
    with pytest.raises(LookupError, match="identity changed"):
        applications.recheck(Application("Tool", "original"))


def test_window_resolution_prioritizes_exact_title_and_identity(monkeypatch):
    manager = WindowManager()
    exact = window(1, "Report", executable="writer.exe")
    partial = window(2, "Report archive", pid=11, created=101, executable="archive.exe")
    monkeypatch.setattr(manager, "windows", lambda: [partial, exact])
    assert manager.resolve("report") == exact
    assert manager.resolve("writer") == exact


def test_window_resolution_fails_on_ambiguity_and_unreliable_identity(monkeypatch):
    manager = WindowManager()
    first = window(1, "Project one")
    second = window(2, "Project two", pid=11, created=101)
    monkeypatch.setattr(manager, "windows", lambda: [first, second])
    with pytest.raises(LookupError, match="ambiguous"):
        manager.resolve("project")
    monkeypatch.setattr(manager, "windows", lambda: [window(created=None)])
    with pytest.raises(LookupError, match="cannot be established"):
        manager.resolve("demo")


def test_application_window_correlation_fails_closed_on_multiple_new_matches(monkeypatch):
    manager = WindowManager()
    first = window(21, "Generated", pid=21, created=201)
    second = window(22, "Generated", pid=22, created=202)
    monkeypatch.setattr(manager, "windows", lambda: [first, second])
    monkeypatch.setattr(manager, "active_window", Mock(side_effect=LookupError("none")))
    monkeypatch.setattr("aria.windows.time.sleep", lambda _seconds: None)
    with pytest.raises(LookupError, match="ambiguously"):
        manager.wait_for_application(Application("Generated", "app.id"), set(), None, timeout=.001)


def test_window_recheck_rejects_reused_handle(monkeypatch):
    manager = WindowManager()
    original = window(handle=7, pid=20, created=200)
    reused = window(handle=7, pid=21, created=201)
    monkeypatch.setattr(manager, "snapshot", lambda _handle: reused)
    with pytest.raises(LookupError, match="identity changed"):
        manager.recheck(original)


class StableWindows:
    def __init__(self):
        self.current = window(handle=7, title="Fixture", rect=Rect(100, 100, 800, 600))
        self.fail_focus = False
        self.work = Rect(-1920, 0, 1920, 1040)

    def windows(self): return [self.current]
    def active(self): return self.current.handle
    def active_window(self): return self.current
    def exists(self, handle): return handle == self.current.handle
    def snapshot(self, handle):
        if handle != self.current.handle: raise LookupError("vanished")
        return self.current
    def recheck(self, target):
        identity = target.identity if isinstance(target, Window) else target
        if identity != self.current.identity: raise LookupError("identity changed")
        return self.current
    def resolve(self, query):
        if query.casefold() not in self.current.title.casefold(): raise LookupError("missing")
        return self.current
    def rect(self, handle): return self.snapshot(handle).rect
    def title(self, handle): return self.snapshot(handle).title
    def work_area(self, target): self.recheck(target); return self.work
    def focus(self, target):
        self.recheck(target)
        if self.fail_focus: raise OSError("focus verification failed")
        self.current = replace(self.current, placement=Placement.NORMAL)
        return self.current
    def show(self, target, mode):
        self.recheck(target)
        placement = {
            "minimize": Placement.MINIMIZED,
            "maximize": Placement.MAXIMIZED,
            "restore": Placement.NORMAL,
        }[mode]
        self.current = replace(self.current, placement=placement)
        return self.current
    def place(self, target, requested):
        self.recheck(target)
        self.current = replace(self.current, rect=requested, placement=Placement.NORMAL)
        return self.current


class StableApps:
    application = Application("Fixture App", "fixture.app")
    def resolve(self, query):
        if query.casefold() != self.application.name.casefold(): raise LookupError("missing")
        return self.application
    def recheck(self, application):
        if application != self.application: raise LookupError("changed")
        return application
    def launch(self, application): return self.recheck(application)


def test_verified_window_operations_update_state_only_after_success():
    windows = StableWindows()
    engine = Engine(windows=windows, applications=StableApps(), shutdown=Mock())
    first = engine.execute(Action(T.FOCUS_WINDOW, "Fixture"))
    assert first.verification == Verification.VERIFIED
    assert engine.state.identity == windows.current.identity
    original = replace(engine.state)
    windows.fail_focus = True
    with pytest.raises(OSError, match="verification failed"):
        engine.execute(Action(T.FOCUS_WINDOW, "Fixture"))
    assert engine.state == original


@pytest.mark.parametrize(("kind", "placement"), [
    (T.MINIMIZE_WINDOW, Placement.MINIMIZED),
    (T.MAXIMIZE_WINDOW, Placement.MAXIMIZED),
    (T.RESTORE_WINDOW, Placement.NORMAL),
])
def test_show_actions_are_verified(kind, placement):
    windows = StableWindows()
    engine = Engine(windows=windows, applications=StableApps(), shutdown=Mock())
    result = engine.execute(Action(kind, "Fixture"))
    assert result.verification == Verification.VERIFIED
    assert windows.current.placement == placement


def test_relative_resize_and_top_right_use_observed_monitor_geometry():
    windows = StableWindows()
    engine = Engine(windows=windows, applications=StableApps(), shutdown=Mock())
    engine.state.update(windows.current.handle, windows.current.title, windows.current.rect,
                        identity=windows.current.identity, placement=windows.current.placement)
    resized = engine.run_text("make it 10% smaller")
    assert resized.verification == Verification.VERIFIED
    assert windows.current.rect.width == 720 and windows.current.rect.height == 540
    moved = engine.run_text("move it to the top right")
    assert moved.verification == Verification.VERIFIED
    assert windows.current.rect.x == -720 and windows.current.rect.y == 0


def test_move_restores_maximized_target_before_placement():
    windows = StableWindows()
    windows.current = replace(windows.current, placement=Placement.MAXIMIZED)
    engine = Engine(windows=windows, applications=StableApps(), shutdown=Mock())
    result = engine.execute(Action(T.MOVE_WINDOW, "Fixture", {"position": "top_right"}))
    assert result.data["restored_before_operation"] is True
    assert result.verification == Verification.VERIFIED


def test_open_path_is_observed_but_explicitly_unverified(tmp_path):
    target = tmp_path / "folder"; target.mkdir()
    files = Files(); files.open = Mock(return_value=target)
    result = Engine(files=files, shutdown=Mock()).execute(Action(T.OPEN_PATH, str(target)))
    assert result.ok and result.observed
    assert result.verification == Verification.UNVERIFIED


def test_known_folder_resolution_uses_windows_value(monkeypatch, tmp_path):
    from aria.filesystem import PathResolver
    resolver = PathResolver(known_provider=lambda name: tmp_path / name)
    (tmp_path / "documents").mkdir()
    assert Files(resolver=resolver).resolve("documents") == tmp_path / "documents"
