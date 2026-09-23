"""Opt-in real Chromium tests against a deterministic local HTTP server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlparse

import pytest

from aria.browser import BrowserConfig, BrowserManager
from aria.core import Action, ActionType as T
from aria.engine import Engine
from aria.permissions import ConfirmationRequired

pytestmark = [
    pytest.mark.browser_integration,
    pytest.mark.skipif(os.environ.get("ARIA_BROWSER_INTEGRATION") != "1",
                       reason="set ARIA_BROWSER_INTEGRATION=1 to launch real Chromium"),
]


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/download":
            body = b"ARIA deterministic browser download\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Disposition", 'attachment; filename="aria-test.txt"')
        elif parsed.path == "/result":
            value = parse_qs(parsed.query).get("query", [""])[0]
            body = f"<h1>Submitted {value}</h1>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif parsed.path == "/page":
            body = b"<h1>Second page</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        else:
            body = b"""<!doctype html><title>ARIA test</title>
                <form action="/result"><label>Command <input name="query"></label>
                <button type="submit">Submit search</button></form>
                <a href="/page">Second page</a>
                <a href="/download">Test file</a>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()


def test_real_browser_navigation_interaction_download_and_cleanup(site, tmp_path):
    manager = BrowserManager(BrowserConfig(
        headless=True, downloads_dir=tmp_path, startup_timeout_ms=20_000,
        navigation_timeout_ms=10_000, element_timeout_ms=5_000, download_timeout_ms=10_000))
    engine = Engine(browser_factory=lambda: manager)
    events = []
    try:
        engine.execute(Action(T.OPEN_WEBSITE, site), on_event=events.append)
        assert manager.state.active and manager.state.current_url == site + "/"
        engine.execute(Action(T.TYPE_IN_BROWSER, "Command", {"text": "hello aria"}), on_event=events.append)
        with pytest.raises(ConfirmationRequired) as request:
            engine.execute(Action(T.SUBMIT_BROWSER, "Submit search", {"role": "button"}), on_event=events.append)
        engine.confirm(request.value.pending.token, on_event=events.append)
        assert "/result?query=hello+aria" in manager.state.current_url

        engine.execute(Action(T.NAVIGATE_BROWSER, site), on_event=events.append)
        engine.execute(Action(T.CLICK_BROWSER_ELEMENT, "Second page", {"role": "link"}), on_event=events.append)
        assert manager.state.current_url.endswith("/page")

        engine.execute(Action(T.NAVIGATE_BROWSER, site), on_event=events.append)
        result = engine.execute(Action(T.DOWNLOAD_FILE, "Test file", {"destination": str(tmp_path)}),
                                on_event=events.append)
        downloaded = Path(result.data["path"])
        assert downloaded.read_text() == "ARIA deterministic browser download\n"
        assert manager.state.last_download == downloaded
        assert "browser_start" in events and "browser_navigation_complete" in events
        assert "browser_interaction_complete" in events and "browser_download_complete" in events
    finally:
        engine.close()
    assert not manager.state.active


def test_closed_page_reports_recovery(site):
    manager = BrowserManager(BrowserConfig(headless=True))
    try:
        manager.execute(Action(T.OPEN_WEBSITE, site))
        manager._page.close()
        with pytest.raises(RuntimeError, match="open browser"):
            manager.execute(Action(T.CLICK_BROWSER_ELEMENT, "Second page", {"role": "link"}))
    finally:
        manager.close()
