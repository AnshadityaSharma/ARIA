"""Opt-in smoke test for live YouTube; failures may indicate external site changes."""
import os
import pytest

from aria.browser import BrowserConfig, BrowserError, BrowserManager
from aria.core import Action, ActionType as T

pytestmark = [
    pytest.mark.external_browser,
    pytest.mark.skipif(os.environ.get("ARIA_EXTERNAL_BROWSER") != "1",
                       reason="set ARIA_EXTERNAL_BROWSER=1 for the live YouTube smoke"),
]


def test_live_youtube_search_and_play():
    browser = BrowserManager(BrowserConfig(
        headless=True, navigation_timeout_ms=30_000, element_timeout_ms=15_000))
    try:
        browser.execute(Action(T.OPEN_WEBSITE, "youtube"))
        try:
            result = browser.execute(Action(T.PLAY_YOUTUBE, "Blinding Lights"))
        except BrowserError as exc:
            if browser.state.current_url and "youtube.com/watch" in browser.state.current_url:
                pytest.xfail(f"external YouTube watch page did not deliver verifiable playback: {exc}")
            raise
        assert "youtube.com/watch" in result.data["url"]
    finally:
        browser.close()
