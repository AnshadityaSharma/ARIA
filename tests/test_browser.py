from pathlib import Path
from unittest.mock import Mock

import pytest

from aria.browser import BrowserConfig, BrowserError, BrowserManager, BrowserState, normalize_url
from aria.core import Action, ActionType as T, RISK, Risk
from aria.engine import Engine
from aria.parser import parse
from aria.permissions import Decision, PermissionEngine
from aria.voice import Transcript, VoiceController


@pytest.mark.parametrize(("command", "kind"), [
    ("open browser", T.OPEN_BROWSER),
    ("open YouTube", T.OPEN_WEBSITE),
    ("open example.com", T.OPEN_WEBSITE),
    ("go to https://example.com/a", T.NAVIGATE_BROWSER),
    ("search the web for aria assistant", T.SEARCH_WEB),
    ("search youtube for blinding lights", T.SEARCH_YOUTUBE),
    ("play blinding lights", T.PLAY_YOUTUBE),
    ("type hello in Search", T.TYPE_IN_BROWSER),
    ("click button Continue", T.CLICK_BROWSER_ELEMENT),
    ("submit Search", T.SUBMIT_BROWSER),
    ("download Test file", T.DOWNLOAD_FILE),
])
def test_browser_parser_actions(command, kind):
    assert parse(command).kind == kind


def test_browser_action_schema_and_risk_are_explicit():
    assert RISK[T.OPEN_WEBSITE] == Risk.NONE
    assert RISK[T.SEARCH_YOUTUBE] == Risk.NONE
    assert RISK[T.PLAY_YOUTUBE] == Risk.NONE
    assert RISK[T.CLICK_BROWSER_ELEMENT] == Risk.LOW
    assert RISK[T.SUBMIT_BROWSER] == Risk.MEDIUM
    assert RISK[T.DOWNLOAD_FILE] == Risk.LOW
    assert PermissionEngine().evaluate(Action(T.DOWNLOAD_FILE, "Test file")) == Decision.ALLOW
    assert PermissionEngine(confirm_low=True).evaluate(Action(T.DOWNLOAD_FILE, "Test file")) == Decision.CONFIRM
    with pytest.raises(ValueError):
        Action(T.CLICK_BROWSER_ELEMENT, "x", {"role": "css"}).validate()
    with pytest.raises(ValueError):
        Action(T.TYPE_IN_BROWSER, "Search").validate()
    with pytest.raises(ValueError):
        Action(T.OPEN_WEBSITE).validate()


@pytest.mark.parametrize(("value", "expected"), [
    ("youtube", "https://www.youtube.com/"),
    ("example.com/path", "https://example.com/path"),
    ("http://127.0.0.1:8080/x", "http://127.0.0.1:8080/x"),
])
def test_url_normalization(value, expected):
    assert normalize_url(value) == expected


@pytest.mark.parametrize("value", [
    "file:///C:/secret.txt", "javascript:alert(1)", "https://user:pass@example.com", "http://:bad",
])
def test_url_validation_rejects_unsafe_or_invalid_values(value):
    with pytest.raises(ValueError):
        normalize_url(value)


def test_browser_is_strictly_lazy_for_desktop_actions():
    factory = Mock()
    engine = Engine(volume=Mock(), browser_factory=factory)
    engine.execute(Action(T.MUTE))
    factory.assert_not_called()
    assert engine.browser_state is None


def test_engine_reuses_browser_and_closes_it():
    browser = Mock()
    browser.state = BrowserState(active=True)
    browser.execute.return_value = __import__("aria.core", fromlist=["Result"]).Result(True, "ok")
    engine = Engine(browser_factory=lambda: browser)
    engine.execute(Action(T.OPEN_BROWSER))
    engine.execute(Action(T.OPEN_WEBSITE, "example.com"))
    assert browser.execute.call_count == 2
    engine.close()
    browser.close.assert_called_once_with()
    assert engine.browser_state is None


def test_missing_browser_page_has_clear_recovery_message():
    manager = BrowserManager(BrowserConfig(headless=True))
    with pytest.raises(BrowserError, match="open browser"):
        manager.execute(Action(T.CLICK_BROWSER_ELEMENT, "Continue", {"role": "button"}))


def test_navigation_does_not_silently_replace_a_lost_session():
    manager = BrowserManager(BrowserConfig(headless=True))
    with pytest.raises(BrowserError, match="open browser"):
        manager.execute(Action(T.NAVIGATE_BROWSER, "https://example.com"))


def test_download_destination_is_optional_but_validated(tmp_path):
    Action(T.DOWNLOAD_FILE, "Test file").validate()
    Action(T.DOWNLOAD_FILE, "Test file", {"destination": str(tmp_path)}).validate()
    with pytest.raises(ValueError):
        Action(T.DOWNLOAD_FILE, "Test file", {"destination": ""}).validate()


def test_timeout_configuration_is_bounded():
    BrowserConfig(startup_timeout_ms=100)
    with pytest.raises(ValueError):
        BrowserConfig(download_timeout_ms=0)


def test_sequential_voice_commands_reuse_the_same_browser_session():
    browser = Mock()
    browser.state = BrowserState(active=True)
    browser.execute.return_value = __import__("aria.core", fromlist=["Result"]).Result(True, "ok")
    engine = Engine(browser_factory=lambda: browser)

    class Mic:
        def capture(self):
            return []

    class ASR:
        phrases = iter((
            "Open YouTube", "Search YouTube for Blinding Lights",
            "Play Blinding Lights", "Download Test file",
        ))
        def transcribe(self, _audio):
            return Transcript(next(self.phrases), .99, "en", .99)

    voice = VoiceController(engine, Mic(), ASR())
    for _ in range(4):
        voice.run_once()
    assert [call.args[0].kind for call in browser.execute.call_args_list] == [
        T.OPEN_WEBSITE, T.SEARCH_YOUTUBE, T.PLAY_YOUTUBE, T.DOWNLOAD_FILE,
    ]
    engine.close()
    browser.close.assert_called_once_with()
