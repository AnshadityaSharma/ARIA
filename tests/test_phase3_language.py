from unittest.mock import Mock

import pytest

from aria.core import Action, ActionType as T, Rect, Verification
from aria.engine import Engine
from aria.intent import Interpreter
from aria.parser import (ClarificationRequired, MalformedCommand,
                         UnsupportedCommand, normalize_command, parse)
from test_core import FakeApps, FakeWindows


@pytest.mark.parametrize(("text", "kind", "target", "params"), [
    ("Could you open the Camera?", T.OPEN_APPLICATION, "Camera", {}),
    ("Please launch Orbit Writer for me", T.OPEN_APPLICATION, "Orbit Writer", {}),
    ("Kindly open the downloads folder", T.OPEN_PATH, "downloads", {}),
    ("Put it in the upper right.", T.MOVE_WINDOW, "tracked", {"position": "top_right"}),
    ("Place that window in the lower left", T.MOVE_WINDOW, "tracked", {"position": "bottom_left"}),
    ("Could you shrink this window slightly?", T.RESIZE_WINDOW, "foreground", {"scale": .9}),
    ("Make current window about a fifth of the screen", T.RESIZE_WINDOW, "foreground", {"screen_ratio": .2}),
    ("Kindly reduce volume by ten percent", T.CHANGE_VOLUME, None, {"delta": -10}),
    ("camera khol do please", T.OPEN_APPLICATION, "camera", {}),
    ("orbit writer kholna", T.OPEN_APPLICATION, "orbit writer", {}),
    ("isko thoda chhota karo", T.RESIZE_WINDOW, "tracked", {"scale": .9}),
    ("is window ko right mein le jao", T.MOVE_WINDOW, "foreground", {"position": "right"}),
])
def test_bounded_deterministic_grammar(text, kind, target, params):
    action = parse(text)
    assert action.kind == kind and action.target == target and dict(action.params) == params


def test_nfkc_control_tokens_and_source_spans_are_preserved():
    normalized = normalize_command("  ｏｐｅｎ   My App  ")
    assert normalized.source == "open   My App"
    assert normalized.control == "open my app"
    assert normalized.surface[normalized.tokens[1].start:normalized.tokens[1].end] == "My"


@pytest.mark.parametrize(("text", "kind", "target"), [
    ("search the web for How to Delete Files and Then Recover Them", T.SEARCH_WEB,
     "How to Delete Files and Then Recover Them"),
    ("search youtube for Open Browser Then Search", T.SEARCH_YOUTUBE,
     "Open Browser Then Search"),
    ("type Don't Delete This in Search Box", T.TYPE_IN_BROWSER, "Search Box"),
])
def test_literal_payloads_preserve_case_and_do_not_trigger_guards(text, kind, target):
    action = parse(text)
    assert action.kind == kind and action.target == target
    if kind == T.TYPE_IN_BROWSER:
        assert action.params["text"] == "Don't Delete This"


@pytest.mark.parametrize("text", [
    "do not open Camera", "don't move it right", "never delete file C:\\Temp\\x.txt",
    "no need to maximize it",
])
def test_negated_commands_never_propose_actions(text):
    with pytest.raises(UnsupportedCommand, match="negated"):
        parse(text)


@pytest.mark.parametrize("text", [
    "open Camera and move it right", "launch browser then search for weather",
    "maximize it and then move it left",
])
def test_compound_commands_require_separate_actions(text):
    with pytest.raises(ClarificationRequired, match="one action"):
        parse(text)


@pytest.mark.parametrize("text", ["open this", "move the thing", "do something with the window"])
def test_ambiguous_commands_have_structured_clarification(text):
    with pytest.raises(ClarificationRequired):
        parse(text)


@pytest.mark.parametrize("text", ["send a message to Alex", "pay my electricity bill", "frobnicate this"])
def test_unsupported_commands_have_structured_abstention(text):
    with pytest.raises(UnsupportedCommand):
        parse(text)


def test_malformed_input_is_distinct():
    with pytest.raises(MalformedCommand): parse("open\nCamera")
    with pytest.raises(MalformedCommand): parse(" ")


def test_recent_reference_expires_after_five_minutes():
    now = [0.0]
    engine = Engine(windows=FakeWindows(), applications=FakeApps(), clock=lambda: now[0])
    engine.run_text("open demo")
    assert engine.state.verified and engine.state.updated_at == 0
    now[0] = 301
    with pytest.raises(ClarificationRequired, match="expired"):
        engine.run_text("move it right")


def test_recent_reference_requires_verified_result():
    class UnverifiedWindows:
        def windows(self): return []
        def active(self): return 7
        def wait_for(self, *_args): return 7
        def rect(self, _handle): return Rect(0, 0, 640, 480)
        def title(self, _handle): return "Unverified"
    class UnverifiedApps:
        def launch(self, _target): return None
    engine = Engine(windows=UnverifiedWindows(), applications=UnverifiedApps())
    result = engine.execute(Action(T.OPEN_APPLICATION, "fixture"))
    assert result.verification == Verification.UNVERIFIED
    assert engine.state.handle is None
    with pytest.raises(ClarificationRequired, match="recent verified"):
        engine.execute(Action(T.MOVE_WINDOW, "tracked", {"position": "right"}))


def test_this_window_uses_command_start_foreground_identity():
    windows = FakeWindows(); engine = Engine(windows=windows, applications=FakeApps())
    result = engine.run_text("move the window right")
    assert result.verification == Verification.VERIFIED
    assert engine.state.identity == windows.snapshot(7).identity


def test_optional_model_never_participates_in_routine_interpretation():
    model = Mock()
    interpreter = Interpreter(model)
    assert interpreter.interpret("Please launch Orbit Writer").kind == T.OPEN_APPLICATION
    with pytest.raises(UnsupportedCommand): interpreter.interpret("compose a poem")
    model.generate.assert_not_called()
