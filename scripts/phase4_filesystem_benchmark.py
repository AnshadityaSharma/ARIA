"""Reproducible Phase 4 measurements using disposable filesystem fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import psutil

from aria.core import Action, ActionType as T
from aria.engine import Engine
from aria.filesystem import Files, PathResolver, same_snapshot, snapshot
from aria.permissions import ConfirmationRequired, describe

ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], percent: int) -> float:
    ordered = sorted(values); position = (len(ordered) - 1) * percent / 100
    low = int(position); high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summary(values: list[float], **details) -> dict:
    return {"samples": len(values), "p50": percentile(values, 50),
            "p95": percentile(values, 95), "mean": statistics.fmean(values), **details}


def timed(operation, count: int) -> list[float]:
    values = []
    for index in range(count):
        started = time.perf_counter_ns(); operation(index)
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    return values


def measure(iterations: int = 30, large_iterations: int = 10) -> dict:
    if iterations < 10 or large_iterations < 3: raise ValueError("Insufficient sample count")
    process = psutil.Process(); timings = {}; scaling = {}
    with tempfile.TemporaryDirectory(prefix="aria-phase4-") as temporary:
        root = Path(temporary); known = root / "known"; known.mkdir()
        resolver = PathResolver(root, known_provider=lambda _name: known)
        files = Files(resolver=resolver); engine = Engine(files=files, shutdown=Mock())
        small = root / "small.bin"; small.write_bytes(os.urandom(4096))
        one_mib = root / "one-mib.bin"; one_mib.write_bytes(os.urandom(1024 * 1024))
        large = root / "large.bin"; large.write_bytes(os.urandom(8 * 1024 * 1024))
        tree = root / "tree"; tree.mkdir()
        for index in range(25): (tree / f"entry-{index:02}.bin").write_bytes(os.urandom(4096))

        timings["path_resolution_absolute"] = timed(lambda _: resolver.existing(str(small)), iterations)
        timings["path_resolution_bare_name"] = timed(lambda _: resolver.existing(small.name), iterations)
        timings["known_folder_resolution"] = timed(lambda _: resolver.existing("documents"), iterations)
        timings["metadata_snapshot_file"] = timed(lambda _: snapshot(small), iterations)
        timings["metadata_manifest_25_entries"] = timed(
            lambda _: snapshot(tree, recursive_metadata=True), iterations)
        for name, path, count in (("4_kib", small, iterations), ("1_mib", one_mib, iterations),
                                  ("8_mib", large, large_iterations)):
            values = timed(lambda _, value=path: snapshot(value, content=True), count)
            scaling[name] = summary(values, bytes=path.stat().st_size, entries=1,
                                    verification="streaming SHA-256 content")
        tree_values = timed(lambda _: snapshot(tree, recursive_metadata=True, content=True), iterations)
        scaling["directory_25_entries"] = summary(tree_values, bytes=25 * 4096, entries=26,
                                                    verification="tree shape plus streaming content")

        move_source = root / "binding-source.bin"; move_source.write_bytes(b"binding")
        move_destination = root / "binding-destination.bin"
        prepared = engine._prepare(Action(T.MOVE_PATH, str(move_source), {"destination": str(move_destination)}))
        bindings = []
        timings["confirmation_binding"] = timed(lambda _: bindings.append(engine._file_binding(prepared)), iterations)
        binding = bindings[-1]
        timings["identity_recheck"] = timed(lambda _: engine._recheck_file_binding(binding), iterations)
        timings["confirmation_display"] = timed(lambda _: describe(prepared), iterations)

        def create_cycle(index):
            name = f"created-{index}"
            result = engine.execute(Action(T.CREATE_FOLDER, str(root), {"name": name}))
            Path(result.data["path"]).rmdir()
        timings["create_and_verify"] = timed(create_cycle, iterations)

        def copy_cycle(index):
            destination = root / f"copy-{index}.bin"
            engine.execute(Action(T.COPY_PATH, str(one_mib), {"destination": str(destination)}))
            destination.unlink()
        timings["copy_1_mib_and_verify"] = timed(copy_cycle, iterations)

        def move_cycle(index):
            source = root / f"move-source-{index}.bin"; source.write_bytes(b"move")
            destination = root / f"move-destination-{index}.bin"
            try: engine.execute(Action(T.MOVE_PATH, str(source), {"destination": str(destination)}))
            except ConfirmationRequired as request: engine.confirm(request.pending.token)
            destination.unlink()
        timings["same_volume_move_and_verify"] = timed(move_cycle, iterations)

        def rename_cycle(index):
            source = root / f"rename-source-{index}.bin"; source.write_bytes(b"rename")
            try: engine.execute(Action(T.RENAME_PATH, str(source), {"destination": f"renamed-{index}.bin"}))
            except ConfirmationRequired as request: engine.confirm(request.pending.token)
            (root / f"renamed-{index}.bin").unlink()
        timings["rename_and_verify"] = timed(rename_cycle, iterations)

        def text_copy_cycle(index):
            destination = root / f"text-copy-{index}.bin"
            engine.run_text(f'copy file "{small}" to "{destination}"')
            destination.unlink()
        timings["full_text_to_verified_copy"] = timed(text_copy_cycle, iterations)

        def text_pending_cycle(index):
            source = root / f"pending-source-{index}.bin"; source.write_bytes(b"pending")
            destination = root / f"pending-destination-{index}.bin"
            try: engine.run_text(f'move file "{source}" to "{destination}"')
            except ConfirmationRequired as request: engine.cancel(request.pending.token)
            source.unlink()
        timings["full_text_to_pending_confirmation"] = timed(text_pending_cycle, iterations)

        startup_command = [sys.executable, "-c", "from aria.filesystem import Files; Files()"]
        timings["fresh_process_startup"] = timed(
            lambda _: subprocess.run(startup_command, check=True, capture_output=True, timeout=10), 10)

        cpu_start = sum(process.cpu_times()[:2]); idle_started = time.perf_counter(); time.sleep(1)
        idle_seconds = time.perf_counter() - idle_started
        idle_cpu = sum(process.cpu_times()[:2]) - cpu_start
        source_bytes = sum(path.stat().st_size for path in (ROOT / "src" / "aria").glob("*.py"))
        pyproject, lockfile = ROOT / "pyproject.toml", ROOT / "uv.lock"
        engine.close()
    return {
        "phase": 4,
        "method": "Disposable local fixtures; perf_counter_ns; linearly interpolated p50/p95. Operation measurements include Engine verification. Hash scaling separates metadata and streaming content work.",
        "environment": {"platform": platform.platform(), "windows_release": platform.release(),
                        "windows_build": platform.version(), "python": platform.python_version(),
                        "processor": platform.processor(), "logical_cpus": psutil.cpu_count(),
                        "physical_memory_gib": psutil.virtual_memory().total / 1073741824},
        "sample_counts": {"standard": iterations, "large_content": large_iterations, "startup": 10},
        "timing_ms": {name: summary(values) for name, values in timings.items()},
        "hashing_and_manifest_scaling_ms": scaling,
        "resources": {"rss_mib": process.memory_info().rss / 1048576,
                      "idle_window_seconds": idle_seconds,
                      "idle_cpu_percent_one_core": 100 * idle_cpu / idle_seconds,
                      "process_count": 1 + len(process.children(recursive=True)),
                      "aria_source_bytes": source_bytes,
                      "pyproject_bytes": pyproject.stat().st_size,
                      "lockfile_bytes": lockfile.stat().st_size,
                      "pyproject_sha256": hashlib.sha256(pyproject.read_bytes()).hexdigest(),
                      "lockfile_sha256": hashlib.sha256(lockfile.read_bytes()).hexdigest()},
        "limits": ["Filesystem caches and antivirus activity are uncontrolled.",
                   "No universal operation latency is claimed; results depend on bytes and entries.",
                   "Cross-volume behavior is contract-tested separately and not timed without a second disposable volume."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--large-iterations", type=int, default=10); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); report = measure(args.iterations, args.large_iterations)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
