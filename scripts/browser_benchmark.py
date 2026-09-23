"""Measure ARIA's lazy browser path against a deterministic local page."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import platform
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlparse

import psutil

from aria.browser import BrowserConfig, BrowserManager
from aria.core import Action, ActionType as T
from aria.engine import Engine
from aria.permissions import ConfirmationRequired


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/download":
            body = b"ARIA browser benchmark\n"
            content_type = "text/plain"
            disposition = 'attachment; filename="aria-browser-benchmark.txt"'
        elif parsed.path == "/result":
            query = parse_qs(parsed.query).get("query", [""])[0]
            body = f"<h1>Submitted {query}</h1>".encode()
            content_type = "text/html; charset=utf-8"
            disposition = None
        else:
            body = (b'<form action="/result"><label>Command <input name="query"></label>'
                    b'<button type="submit">Submit search</button></form>'
                    b'<a href="/download">Test file</a>')
            content_type = "text/html; charset=utf-8"
            disposition = None
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def tree(process):
    return [process, *process.children(recursive=True)]


def resources(process):
    processes = tree(process)
    rss = sum(item.memory_info().rss for item in processes if item.is_running())
    return {"processes": len(processes), "rss_mb": round(rss / 1024 / 1024, 2)}


def cpu_sample(process, seconds=1.0):
    processes = tree(process)
    for item in processes:
        try:
            item.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(seconds)
    total = 0.0
    for item in processes:
        try:
            total += item.cpu_percent(None)
        except psutil.Error:
            pass
    return round(total, 2)


def elapsed(action):
    started = time.perf_counter()
    result = action()
    return result, round((time.perf_counter() - started) * 1000, 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("logs/browser-baseline.json"))
    args = parser.parse_args()
    process = psutil.Process()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    events = {}

    def event(name):
        events[name] = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="aria-browser-benchmark-") as folder:
        config = BrowserConfig(headless=True, downloads_dir=Path(folder))
        manager = BrowserManager(config)
        before = resources(process)
        before["cpu_percent_1s"] = cpu_sample(process)
        init_start = time.perf_counter()
        engine = Engine(browser_factory=lambda: manager)
        engine_init_ms = round((time.perf_counter() - init_start) * 1000, 3)
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            _, open_ms = elapsed(lambda: engine.execute(Action(T.OPEN_WEBSITE, url), on_event=event))
            active = resources(process)
            active["cpu_percent_1s"] = cpu_sample(process)
            _, type_ms = elapsed(lambda: engine.execute(
                Action(T.TYPE_IN_BROWSER, "Command", {"text": "benchmark"}), on_event=event))

            def submit():
                try:
                    engine.execute(Action(T.SUBMIT_BROWSER, "Submit search", {"role": "button"}), on_event=event)
                except ConfirmationRequired as request:
                    return engine.confirm(request.pending.token, on_event=event)

            _, submit_ms = elapsed(submit)
            engine.execute(Action(T.NAVIGATE_BROWSER, url), on_event=event)
            download, download_ms = elapsed(lambda: engine.execute(
                Action(T.DOWNLOAD_FILE, "Test file", {"destination": folder}), on_event=event))
            browser_startup_ms = round((events["browser_ready"] - events["browser_start"]) * 1000, 3)
            navigation_ms = round((events["browser_navigation_complete"] - events["browser_navigation_start"]) * 1000, 3)
            download_verified = Path(download.data["path"]).is_file()
        finally:
            engine.close()
            server.shutdown()
            thread.join(2)
            server.server_close()
        deadline = time.monotonic() + 5
        while len(tree(process)) > 1 and time.monotonic() < deadline:
            time.sleep(.1)
        after = resources(process)
        data = {
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "lazy_engine_init_ms": engine_init_ms,
            "without_browser": before,
            "with_browser": active,
            "browser_startup_ms": browser_startup_ms,
            "initial_open_and_navigation_ms": open_ms,
            "last_navigation_ms": navigation_ms,
            "type_ms": type_ms,
            "confirmed_submit_ms": submit_ms,
            "download_ms": download_ms,
            "download_verified": download_verified,
            "after_cleanup": after,
            "event_offsets_ms": {
                name: round((stamp - min(events.values())) * 1000, 3)
                for name, stamp in events.items()
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
