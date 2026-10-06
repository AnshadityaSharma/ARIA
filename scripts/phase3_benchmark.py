"""Reproducible, controlled Phase 3 deterministic-language measurements."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

import psutil

from aria.desktop import Application, Applications
from aria.intent import Interpreter
from aria.parser import ClarificationRequired, UnsupportedCommand, _number, normalize_command, parse
from scripts.phase0_eval import ROOT, controlled_engine


def percentile(values: list[float], percent: int) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summary(values: list[float]) -> dict:
    return {
        "samples": len(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "mean": statistics.fmean(values),
    }


def timed(operation, count: int) -> list[float]:
    values = []
    for _ in range(count):
        started = time.perf_counter_ns()
        operation()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    return values


def expected_error(operation, kind: type[Exception]) -> None:
    try:
        operation()
    except kind:
        return
    raise AssertionError(f"Expected {kind.__name__}")


class DiscoveredApplications(Applications):
    """In-memory output of discovery, with production resolution unchanged."""

    def __init__(self):
        super().__init__()
        self.items = [
            Application("Orbit Writer", "fixture.orbit"),
            Application("Orbit Viewer", "fixture.viewer"),
            Application("Northwind Notes", "fixture.notes"),
        ]

    def discover(self):
        return list(self.items)


def _source_bytes() -> int:
    return sum(path.stat().st_size for path in (ROOT / "src" / "aria").glob("*.py"))


def measure(iterations: int = 2000, startup_iterations: int = 10) -> dict:
    if iterations < 100 or startup_iterations < 1:
        raise ValueError("Use at least 100 warm iterations and one startup iteration")
    process = psutil.Process()
    interpreter = Interpreter()
    applications = DiscoveredApplications()
    engine = controlled_engine({"tracked_window": 7, "foreground_window": 9})
    timing: dict[str, list[float]] = {}
    try:
        cold_started = time.perf_counter_ns()
        cold_action = interpreter.interpret("Would you start Orbit Writer for me")
        cold = (time.perf_counter_ns() - cold_started) / 1_000_000
        if cold_action.target != "Orbit Writer":
            raise AssertionError("Cold interpretation returned the wrong target")

        timing["normalization"] = timed(
            lambda: normalize_command("  Kindly make that twenty percent smaller.  "), iterations)
        timing["grammar_direct"] = timed(lambda: parse("open Orbit Writer"), iterations)
        timing["grammar_paraphrase"] = timed(
            lambda: parse("Would you start Orbit Writer for me"), iterations)
        timing["grammar_hinglish"] = timed(lambda: parse("usko thoda bada karo"), iterations)
        timing["parameter_numeric_conversion"] = timed(lambda: _number("twenty"), iterations)
        timing["parameter_command_parse"] = timed(
            lambda: parse("make it twenty percent smaller"), iterations)
        timing["state_reference_resolution"] = timed(lambda: engine._handle("tracked"), iterations)
        timing["application_exact_resolution"] = timed(
            lambda: applications.resolve("Orbit Writer"), iterations)
        timing["application_compact_resolution"] = timed(
            lambda: applications.resolve("orbitwriter"), iterations)
        timing["application_typo_resolution"] = timed(
            lambda: applications.resolve("orbitwritr"), iterations)
        timing["full_interpretation_direct"] = timed(
            lambda: interpreter.interpret("open Orbit Writer"), iterations)
        timing["full_interpretation_paraphrase"] = timed(
            lambda: interpreter.interpret("Would you start Orbit Writer for me"), iterations)
        timing["full_interpretation_hinglish"] = timed(
            lambda: interpreter.interpret("usko thoda bada karo"), iterations)
        timing["clarification"] = timed(
            lambda: expected_error(lambda: interpreter.interpret("shift the object"),
                                   ClarificationRequired), iterations)
        timing["abstention"] = timed(
            lambda: expected_error(lambda: interpreter.interpret("never move it left"),
                                   UnsupportedCommand), iterations)

        startup_command = [sys.executable, "-c", "from aria.intent import Interpreter; Interpreter().interpret('open Calculator')"]
        timing["fresh_process_startup_and_interpretation"] = timed(
            lambda: subprocess.run(startup_command, check=True, capture_output=True, timeout=10),
            startup_iterations)

        cpu_start = sum(process.cpu_times()[:2])
        idle_started = time.perf_counter()
        time.sleep(1)
        idle_seconds = time.perf_counter() - idle_started
        idle_cpu = sum(process.cpu_times()[:2]) - cpu_start
        pyproject = ROOT / "pyproject.toml"
        lockfile = ROOT / "uv.lock"
        return {
            "phase": 3,
            "method": (
                "Single-process warm samples use perf_counter_ns and linear-interpolated p50/p95; "
                "cold interpretation is the first call; startup uses fresh subprocesses. Dynamic "
                "application matching and state resolution use inert discovered records and stable fake windows."
            ),
            "environment": {
                "platform": platform.platform(),
                "windows_release": platform.release(),
                "windows_build": platform.version(),
                "python": platform.python_version(),
                "processor": platform.processor(),
                "logical_cpus": psutil.cpu_count(),
                "physical_memory_gib": psutil.virtual_memory().total / 1073741824,
            },
            "sample_counts": {"warm": iterations, "startup": startup_iterations, "cold": 1},
            "cold_interpretation_ms": cold,
            "timing_ms": {name: summary(values) for name, values in timing.items()},
            "objectives_ms": {
                "warm_interpretation_p50": 0.05,
                "warm_interpretation_p95": 0.10,
                "status": "proposed diagnostic objectives, not guaranteed facts",
            },
            "resources": {
                "rss_mib": process.memory_info().rss / 1048576,
                "idle_window_seconds": idle_seconds,
                "idle_cpu_percent_one_core": 100 * idle_cpu / idle_seconds,
                "process_count": 1 + len(process.children(recursive=True)),
                "aria_source_bytes": _source_bytes(),
                "pyproject_bytes": pyproject.stat().st_size,
                "lockfile_bytes": lockfile.stat().st_size,
                "pyproject_sha256": hashlib.sha256(pyproject.read_bytes()).hexdigest(),
                "lockfile_sha256": hashlib.sha256(lockfile.read_bytes()).hexdigest(),
            },
        }
    finally:
        engine.close()
        interpreter.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--startup-iterations", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = measure(args.iterations, args.startup_iterations)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
