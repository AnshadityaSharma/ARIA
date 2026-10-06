"""Owned CPU-only llama.cpp server. No remote endpoint, tools, or automatic downloads."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import http.client
import json
import logging
import math
import os
import queue
import secrets
import socket
import subprocess
import threading
import time

from aria.intent import IntentError


@dataclass(frozen=True)
class IntentConfig:
    model: Path
    runtime: Path = Path(".aria-runtime/b11126/llama-server.exe")
    timeout: float = 20
    load_timeout: float = 60
    max_tokens: int = 128
    threads: int = 4

    def __post_init__(self):
        for value in (self.timeout, self.load_timeout):
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= 300:
                raise ValueError("Intent timeouts must be between 0 and 300 seconds")
        if type(self.max_tokens) is not int or not 16 <= self.max_tokens <= 512:
            raise ValueError("Intent token limit must be 16..512")
        if type(self.threads) is not int or not 1 <= self.threads <= 32:
            raise ValueError("Intent CPU threads must be 1..32")


class LocalIntentModel:
    def __init__(self, config: IntentConfig):
        self.config = config
        self.process = None
        self.port = None
        self.key = secrets.token_urlsafe(32)
        self.closed = threading.Event()
        self._lock = threading.Lock()
        self._process_lock = threading.Lock()
        self.last_metrics = {}

    def _launch(self):
        with self._process_lock:
            if self.closed.is_set():
                raise IntentError("Local intent model was closed.")
            if not Path(self.config.model).is_file() or not Path(self.config.runtime).is_file():
                raise IntentError("Local intent model unavailable; provision the model and runtime first.")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                self.port = probe.getsockname()[1]
            args = [str(Path(self.config.runtime).resolve()), "-m", str(Path(self.config.model).resolve()),
                    "--host", "127.0.0.1", "--port", str(self.port), "--api-key", self.key,
                    "--offline", "--no-webui", "--no-agent", "--no-slots",
                    "-ngl", "0", "--threads", str(self.config.threads),
                    "--ctx-size", "2048", "--parallel", "1"]
            self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def _request(self, path, payload=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1 if payload is None else self.config.timeout)
        try:
            connection.request("GET" if payload is None else "POST", path,
                               body=None if payload is None else json.dumps(payload).encode(),
                               headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read(65537)
            if response.status != 200 or len(data) > 65536:
                raise IntentError("Local model returned an invalid response.")
            return json.loads(data)
        finally:
            connection.close()

    def _stop(self):
        with self._process_lock:
            process, self.process = self.process, None
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=3)

    def _ensure_loaded(self, event):
        if self.closed.is_set():
            raise IntentError("Local intent model was closed.")
        if self.process is not None and self.process.poll() is None:
            return
        started = time.perf_counter()
        event("model_load_start")
        self._launch()
        try:
            while time.perf_counter() - started < self.config.load_timeout:
                if self.closed.is_set():
                    raise IntentError("Local intent model was closed.")
                if self.process is None or self.process.poll() is not None:
                    raise IntentError("Local intent model exited during startup. Check runtime dependencies and Windows Application Control; do not disable security protections.")
                try:
                    health = self._request("/health")
                    if isinstance(health, dict) and health.get("status") == "ok":
                        self.last_metrics["load_ms"] = (time.perf_counter()-started)*1000
                        event("model_load_complete")
                        return
                except (OSError, ValueError, IntentError):
                    pass
                self.closed.wait(.05)
            raise IntentError("Local intent model loading timed out; nothing was executed.")
        except BaseException:
            self._stop()
            raise

    def generate(self, text, prompt, schema, *, on_event=None):
        def event(name):
            logging.getLogger("aria.intent").info("model_event=%s timestamp=%.6f", name, time.perf_counter())
            if on_event is not None:
                on_event(name)
        # Concurrent interpretation is not a queue of deferred actions.
        if not self._lock.acquire(blocking=False):
            raise IntentError("Local intent model is busy; try again after this command.")
        try:
            self.last_metrics = {}
            self._ensure_loaded(event)
            start = time.perf_counter()
            event("model_start")
            payload = {
                "prompt": f"<|im_start|>system\n{prompt}<|im_end|>\n<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n",
                "n_predict": self.config.max_tokens, "temperature": 0, "seed": 0,
                "cache_prompt": True, "stream": False, "stop": ["<|im_end|>"],
                "json_schema": schema,
            }
            answers = queue.Queue(maxsize=1)
            def request():
                try:
                    answers.put((True, self._request("/completion", payload)))
                except Exception as exc:
                    answers.put((False, exc))
            worker = threading.Thread(target=request, name="aria-intent-http", daemon=True)
            worker.start()
            try:
                success, response = answers.get(timeout=self.config.timeout)
            except queue.Empty as exc:
                self._stop()  # Cancel computation, not just waiting for its result.
                worker.join(timeout=1)
                event("model_timeout")
                raise IntentError("Local intent model timed out; nothing was executed.") from exc
            self.last_metrics["inference_ms"] = (time.perf_counter()-start)*1000
            if self.closed.is_set():
                raise IntentError("Local intent model was closed; nothing was executed.")
            if not success:
                self._stop()
                if isinstance(response, TimeoutError):
                    event("model_timeout")
                    raise IntentError("Local intent model timed out; nothing was executed.") from response
                raise IntentError("Local intent model failed; nothing was executed.") from response
            if not isinstance(response, dict) or response.get("stop_type") not in {"eos", "word"}:
                raise IntentError("Local intent model exceeded its output limit or returned incomplete output.")
            content = response.get("content")
            if not isinstance(content, str) or len(content) > 8192:
                raise IntentError("Local intent model exceeded its output limit.")
            self.last_metrics.update(input_tokens=response.get("tokens_evaluated"),
                                     output_tokens=response.get("tokens_predicted"),
                                     timings=response.get("timings"))
            event("model_complete")
            return content
        except OSError as exc:
            self._stop()
            raise IntentError("Local intent model unavailable; check the local installation.") from exc
        finally:
            logging.getLogger("aria.intent").info("model_metrics=%s", self.last_metrics)
            self._lock.release()

    def close(self):
        self.closed.set()
        self._stop()
