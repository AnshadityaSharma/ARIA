"""Reproducible Phase 1 kernel timings with an inert volume adapter."""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path
from unittest.mock import Mock

import psutil

from aria.core import Action, ActionType
from aria.engine import Engine
from aria.desktop import AudioState
from aria.permissions import PermissionEngine
from aria.permissions import ConfirmationRequired


def percentile(values, pct):
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def measure(iterations=1000):
    if iterations < 20:
        raise ValueError("At least 20 iterations are required")
    process = psutil.Process()
    volume = Mock()
    volume.mute.return_value = AudioState(40, True, "inert-endpoint")
    engine = Engine(volume=volume, shutdown=Mock())
    action = Action(ActionType.MUTE)
    for _ in range(20):
        engine.execute(action)
    timings = {name: [] for name in ("validation", "risk", "execution", "verification",
                                    "target_recheck", "full_kernel", "confirmed_kernel")}
    spans = {"validation": ("validation_start", "validation_complete"),
             "risk": ("risk_start", "risk_decision"),
             "execution": ("execution_start", "execution_complete"),
             "verification": ("verification_start", "verification_complete")}
    for _ in range(iterations):
        events = {}
        start = time.perf_counter_ns()
        engine.execute(action, on_event=lambda name: events.__setitem__(name, time.perf_counter_ns()))
        timings["full_kernel"].append((time.perf_counter_ns() - start) / 1_000_000)
        for name, (begin, end) in spans.items():
            timings[name].append((events[end] - events[begin]) / 1_000_000)
    guarded = Engine(volume=volume, shutdown=Mock(), permissions=PermissionEngine())
    confirmed_action = Action(ActionType.SHUTDOWN)
    for _ in range(iterations):
        try:
            guarded.execute(confirmed_action)
        except ConfirmationRequired as required:
            token = required.pending.token
        else:
            raise AssertionError("SHUTDOWN did not require confirmation")
        events = {}
        start = time.perf_counter_ns()
        guarded.confirm(token, on_event=lambda name: events.__setitem__(name, time.perf_counter_ns()))
        timings["confirmed_kernel"].append((time.perf_counter_ns() - start) / 1_000_000)
        timings["target_recheck"].append((events["target_recheck_complete"] - events["target_recheck_start"]) / 1_000_000)
    cpu_start = sum(process.cpu_times()[:2])
    idle_start = time.perf_counter()
    time.sleep(1)
    idle_seconds = time.perf_counter() - idle_start
    idle_cpu = sum(process.cpu_times()[:2]) - cpu_start
    engine.close()
    guarded.close()
    return {
        "phase": 1,
        "method": "Warm typed MUTE action through Engine with inert volume adapter; confirmed SHUTDOWN with inert shutdown adapter measures target recheck. No parser, browser, microphone, or real OS action.",
        "environment": {"platform": platform.platform(), "python": platform.python_version(),
                        "processor": platform.processor(), "logical_cpus": psutil.cpu_count()},
        "iterations": iterations,
        "timing_ms": {name: {"p50": percentile(samples, 50), "p95": percentile(samples, 95),
                              "mean": statistics.fmean(samples)} for name, samples in timings.items()},
        "resources": {"rss_mib": process.memory_info().rss / 1048576,
                      "idle_window_seconds": idle_seconds,
                      "idle_cpu_percent_one_core": 100 * idle_cpu / idle_seconds,
                      "process_count": 1 + len(process.children(recursive=True))},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = measure(args.iterations)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
