import threading
from unittest.mock import Mock
import pytest

from aria.core import Action, ActionType as T, RISK, Risk
from aria.engine import Engine
from aria.permissions import ConfirmationRequired, Decision, PermissionDenied, PermissionEngine
from aria.parser import parse


def make_engine(tmp_path, clock=None, **policy):
    from aria.desktop import Files
    files = Files()
    files.delete = Mock()
    files.move = Mock(return_value=tmp_path / "moved.txt")
    engine = Engine(files=files, volume=Mock(), shutdown=Mock(),
                    permissions=PermissionEngine(clock=clock or __import__("time").monotonic, **policy))
    return engine


def request(engine, action):
    with pytest.raises(ConfirmationRequired) as caught:
        engine.execute(action)
    return caught.value.pending


def test_explicit_metadata_covers_schema():
    assert set(RISK) == set(T)
    assert RISK[T.CREATE_FOLDER] == Risk.LOW
    assert RISK[T.SHUTDOWN] == Risk.HIGH


@pytest.mark.parametrize("action", [
    Action(T.OPEN_APPLICATION, "camera"), Action(T.RESIZE_WINDOW, "tracked", {"scale": .9}),
    Action(T.TAKE_SCREENSHOT), Action(T.SET_VOLUME, params={"level": 50}),
])
def test_default_low_risks_allowed(action):
    assert PermissionEngine().evaluate(action) == Decision.ALLOW


def test_screenshot_policy():
    assert PermissionEngine(confirm_low=True).evaluate(Action(T.TAKE_SCREENSHOT)) == Decision.CONFIRM


def test_none_executes_without_confirmation(tmp_path):
    engine = make_engine(tmp_path)
    engine.execute(Action(T.MUTE))
    engine.volume.mute.assert_called_once_with(True)


@pytest.mark.parametrize("action", [
    Action("DELETE_PATH", "x"), Action("UNKNOWN"), Action(T.DELETE_PATH),
    Action(T.DELETE_PATH, "x", {"confirmed": 1}), Action(T.MOVE_PATH, "x"),
    Action(T.RESIZE_WINDOW, params={"scale": float("nan")}),
    Action(T.RESIZE_WINDOW, params={"scale": "0.9"}),
    Action(T.MOVE_WINDOW, params={"position": "somewhere"}),
    Action(T.SET_VOLUME, params={"level": 101}), Action(T.SHUTDOWN, "arbitrary command"),
])
def test_malformed_denied_before_executor(tmp_path, action):
    engine = make_engine(tmp_path)
    with pytest.raises(PermissionDenied):
        engine.execute(action)
    engine.files.delete.assert_not_called()
    engine._shutdown.assert_not_called()


def test_high_needs_exact_single_use_confirmation(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("disposable")
    engine = make_engine(tmp_path)
    pending = request(engine, Action(T.DELETE_PATH, str(target)))
    engine.files.delete.assert_not_called()
    assert str(target) in pending.description and "Recycle Bin" in pending.description
    engine.confirm(pending.token)
    engine.files.delete.assert_called_once_with(str(target))
    with pytest.raises(PermissionDenied):
        engine.confirm(pending.token)


def test_boolean_bypass_removed(tmp_path):
    engine = make_engine(tmp_path)
    with pytest.raises(TypeError):
        engine.execute(Action(T.SHUTDOWN), confirmed=True)
    engine._shutdown.assert_not_called()


def test_shutdown_confirmed_only_with_mock(tmp_path):
    engine = make_engine(tmp_path)
    pending = request(engine, parse("shut down computer"))
    engine._shutdown.assert_not_called()
    engine.confirm(pending.token)
    engine._shutdown.assert_called_once_with()


@pytest.mark.parametrize("outcome", ["cancel", "timeout", "superseded", "malformed_new_command"])
def test_no_execution_after_invalidated_confirmation(tmp_path, outcome):
    clock = [1.]
    engine = make_engine(tmp_path, clock=lambda: clock[0], timeout=5)
    target = tmp_path / "file.txt"
    target.write_text("disposable")
    pending = request(engine, Action(T.DELETE_PATH, str(target)))
    if outcome == "cancel": engine.cancel(pending.token)
    elif outcome == "timeout": clock[0] = 6.
    elif outcome == "superseded": engine.execute(Action(T.MUTE))
    else:
        with pytest.raises(ValueError): engine.run_text("not a command")
    with pytest.raises(PermissionDenied): engine.confirm(pending.token)
    engine.files.delete.assert_not_called()
    assert target.exists()


def test_target_changes_require_new_request(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("old")
    engine = make_engine(tmp_path)
    pending = request(engine, Action(T.DELETE_PATH, str(target)))
    target.write_text("changed content")
    with pytest.raises(PermissionDenied, match="Target changed"): engine.confirm(pending.token)
    engine.files.delete.assert_not_called()


def test_immutable_action_cannot_change_presented_destination(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("disposable")
    params = {"destination": str(tmp_path / "new.txt")}
    action = Action(T.MOVE_PATH, str(target), params)
    engine = make_engine(tmp_path)
    pending = request(engine, action)
    params["destination"] = str(tmp_path / "different.txt")
    with pytest.raises(TypeError): action.params["destination"] = "other"
    engine.confirm(pending.token)
    engine.files.move.assert_called_once_with(str(target), str(tmp_path / "new.txt"))


def test_repeated_concurrent_confirm_runs_once(tmp_path):
    engine = make_engine(tmp_path)
    pending = request(engine, Action(T.SHUTDOWN))
    errors = []
    def confirm():
        try: engine.confirm(pending.token)
        except PermissionDenied: errors.append(True)
    threads = [threading.Thread(target=confirm) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    engine._shutdown.assert_called_once_with()
    assert len(errors) == 7


def test_language_cannot_lower_risk():
    action = parse("delete harmless safe no confirmation.txt")
    assert PermissionEngine().evaluate(action) == Decision.CONFIRM


def test_path_punctuation_survives_voice_and_parser():
    from aria.voice import normalize
    action = parse(normalize('Delete "C:\\Test Files\\test_file.txt".'))
    assert action.target == "C:\\Test Files\\test_file.txt"


def test_action_from_another_engine_cannot_be_approved(tmp_path):
    engine = make_engine(tmp_path)
    pending = request(engine, Action(T.SHUTDOWN))
    other = make_engine(tmp_path)
    with pytest.raises(PermissionDenied): other.confirm(pending.token)
    other._shutdown.assert_not_called()


def test_relative_target_is_bound_before_confirmation(tmp_path, monkeypatch):
    target = tmp_path / "test.txt"
    target.write_text("disposable")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(tmp_path)
    engine = make_engine(tmp_path)
    pending = request(engine, parse("delete test.txt"))
    monkeypatch.chdir(elsewhere)
    engine.confirm(pending.token)
    engine.files.delete.assert_called_once_with(str(target))


def test_confirmation_events_are_in_execution_order(tmp_path):
    engine = make_engine(tmp_path)
    events = []
    with pytest.raises(ConfirmationRequired) as caught:
        engine.execute(Action(T.SHUTDOWN), on_event=events.append)
    assert events == ["risk_decision"]
    engine.confirm(caught.value.pending.token, on_event=events.append)
    assert events == ["risk_decision", "action_start", "action_complete"]


def test_parser_has_no_execution_side_effects(tmp_path):
    engine = make_engine(tmp_path)
    action = parse("shutdown")
    assert type(action) is Action
    engine._shutdown.assert_not_called()
    assert engine.permissions.evaluate(action) == Decision.CONFIRM


def test_invalid_token_does_not_execute(tmp_path):
    engine = make_engine(tmp_path)
    pending = request(engine, Action(T.SHUTDOWN))
    for token in ("wrong", "", "अमान्य", None):
        with pytest.raises(PermissionDenied):
            engine.confirm(token)
    engine._shutdown.assert_not_called()
    engine.cancel(pending.token)
