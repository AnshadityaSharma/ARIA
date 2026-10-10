"""Phase 5 screenshot/audio timing. Native mode captures then deletes a disposable PNG."""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import psutil
from PIL import Image

from aria.core import Action, ActionType as T, Verification
from aria.desktop import AudioState
from aria.engine import Engine


class InertVolume:
    """No real output device is read or changed in controlled measurements."""
    def __init__(self):
        self.level = 50
        self.muted = False
    def _state(self): return AudioState(self.level, self.muted, "inert-endpoint")
    def set(self, level): self.level = max(0, min(100, level)); return self._state()
    def change(self, delta): self.level = max(0, min(100, self.level + delta)); return self._state()
    def mute(self, value): self.muted = value; return self._state()


def percentile(values, pct):
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def measure(iterations=20, native_screenshot=False):
    if iterations < 10:
        raise ValueError("At least 10 iterations are required")
    process = psutil.Process()
    engine = Engine(volume=InertVolume())
    samples = {name: [] for name in ("screenshot", "set_volume", "change_volume", "mute", "unmute")}
    dimensions = None
    started_cpu = sum(process.cpu_times()[:2])
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="aria-phase5-") as folder:
        root = Path(folder)
        def screenshot_once(index):
            nonlocal dimensions
            path = root / f"shot-{index}.png"
            begin = time.perf_counter()
            result = engine.execute(Action(T.TAKE_SCREENSHOT, str(path)))
            samples["screenshot"].append((time.perf_counter() - begin) * 1000)
            if result.verification != Verification.VERIFIED:
                raise RuntimeError("Screenshot was not verified")
            dimensions = [result.data["width"], result.data["height"]]
            path.unlink()

        if native_screenshot:
            for index in range(iterations): screenshot_once(index)
        else:
            with patch("PIL.ImageGrab.grab", side_effect=lambda **_kwargs: Image.new("RGB", (64, 40), "navy")), \
                    patch("aria.desktop._virtual_desktop_size", return_value=(64, 40)):
                for index in range(iterations): screenshot_once(index)
        actions = {
            "set_volume": Action(T.SET_VOLUME, params={"level": 50}),
            "change_volume": Action(T.CHANGE_VOLUME, params={"delta": 10}),
            "mute": Action(T.MUTE),
            "unmute": Action(T.UNMUTE),
        }
        for _ in range(iterations):
            for name, action in actions.items():
                begin = time.perf_counter()
                result = engine.execute(action)
                samples[name].append((time.perf_counter() - begin) * 1000)
                if result.verification != Verification.VERIFIED:
                    raise RuntimeError(f"{name} was not verified")
    wall = time.perf_counter() - started
    cpu = sum(process.cpu_times()[:2]) - started_cpu
    return {
        "method": "Engine guarded actions; native disposable screenshot" if native_screenshot else
                  "Engine guarded actions; mocked image capture and inert audio endpoint",
        "environment": {"platform": platform.platform(), "python": platform.python_version(),
                        "processor": platform.processor(), "logical_cpus": psutil.cpu_count()},
        "iterations_per_action": iterations,
        "timing_ms": {name: {"p50": percentile(values, 50), "p95": percentile(values, 95),
                             "mean": statistics.fmean(values)} for name, values in samples.items()},
        "last_screenshot_dimensions": dimensions,
        "resources": {"rss_mib_after": process.memory_info().rss / 1048576,
                      "cpu_seconds_over_run": cpu, "wall_seconds": wall,
                      "process_count_after": 1 + len(process.children(recursive=True))},
        "note": "Audio operations always use an inert endpoint; no real speaker settings are changed.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--native-screenshot", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = measure(args.iterations, args.native_screenshot)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
