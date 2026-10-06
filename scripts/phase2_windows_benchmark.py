"""Reproducible Phase 2 Windows discovery/control measurements."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import uuid
from pathlib import Path

import psutil

from aria.core import Action, ActionType as T
from aria.desktop import Applications, Files, known_folder
from aria.engine import Engine
from aria.windows import WindowManager


def percentile(values: list[float], pct: int) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    low = int(position); high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summary(samples: list[float]) -> dict:
    return {"samples": len(samples), "p50": percentile(samples, 50),
            "p95": percentile(samples, 95), "mean": statistics.fmean(samples)}


def timed(operation, count: int) -> list[float]:
    values = []
    for _ in range(count):
        started = time.perf_counter_ns(); operation()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    return values


def timed_prepared(prepare, operation, count: int) -> list[float]:
    values = []
    for _ in range(count):
        prepare()
        started = time.perf_counter_ns(); operation()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    return values


def _shortcut(path: Path, target: Path, arguments: str) -> None:
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ARIA_BENCH_SHORTCUT);"
        "$s.TargetPath=$env:ARIA_BENCH_TARGET;$s.Arguments=$env:ARIA_BENCH_ARGUMENTS;"
        "$s.WorkingDirectory=$env:ARIA_BENCH_WORKING;$s.Save()"
    )
    environment = os.environ.copy()
    environment.update({"ARIA_BENCH_SHORTCUT": str(path), "ARIA_BENCH_TARGET": str(target),
                        "ARIA_BENCH_ARGUMENTS": arguments, "ARIA_BENCH_WORKING": str(target.parent)})
    subprocess.run(["powershell", "-NoProfile", "-Command", script], env=environment,
                   check=True, timeout=10, capture_output=True)


def _wait_gone(manager: WindowManager, handle: int) -> None:
    deadline = time.monotonic() + 3
    while manager.exists(handle) and time.monotonic() < deadline:
        time.sleep(.05)


class InertFiles(Files):
    def open(self, value: str) -> Path:
        return self.resolve(value)


def measure(iterations: int = 30, launch_iterations: int = 3) -> dict:
    if iterations < 10 or launch_iterations < 1:
        raise ValueError("Use at least 10 iterations and one launch iteration")
    process = psutil.Process(); manager = WindowManager(); applications = Applications()
    root = tk.Tk(); title = f"ARIA benchmark {uuid.uuid4().hex}"
    root.title(title); root.geometry("800x600+120+120"); root.update()
    initial = manager.resolve(title)
    engine = Engine(windows=manager)
    engine.state.update(initial.handle, initial.title, initial.rect, identity=initial.identity,
                        executable=initial.executable, application_id=initial.application_id,
                        placement=initial.placement)
    timings: dict[str, list[float]] = {}
    launch_status = "not run"
    shortcut = None
    try:
        timings["application_discovery_cold"] = timed(applications.discover, 1)
        timings["application_discovery_warm"] = timed(applications.discover, min(iterations, 10))
        timings["window_enumeration"] = timed(manager.windows, iterations)
        timings["window_target_resolution"] = timed(lambda: manager.resolve(title), iterations)
        target = manager.resolve(title)
        timings["window_identity_recheck"] = timed(lambda: manager.recheck(target), iterations)
        timings["known_folder_resolution"] = timed(lambda: known_folder("documents"), iterations)

        # PowerShell discovery can temporarily take foreground ownership. Return
        # it to the disposable fixture before measuring native focus verification.
        root.attributes("-topmost", True); root.lift(); root.focus_force(); root.update()
        root.attributes("-topmost", False); root.update()

        actions = {
            "move_verification": Action(T.MOVE_WINDOW, "tracked", {"position": "right", "pixels": 1}),
            "resize_verification": Action(T.RESIZE_WINDOW, "tracked", {"scale": .99}),
            "minimize_verification": Action(T.MINIMIZE_WINDOW, "tracked"),
            "maximize_verification": Action(T.MAXIMIZE_WINDOW, "tracked"),
            "restore_verification": Action(T.RESTORE_WINDOW, "tracked"),
        }
        def prepare_focus():
            root.deiconify(); root.attributes("-topmost", True); root.lift(); root.focus_force(); root.update()
            root.attributes("-topmost", False); root.update()
        timings["focus_verification"] = timed_prepared(
            prepare_focus, lambda: engine.execute(Action(T.FOCUS_WINDOW, "tracked")), min(iterations, 10))
        for name, action in actions.items():
            count = min(iterations, 10) if "verification" in name else iterations
            timings[name] = timed(lambda value=action: engine.execute(value), count)
            if name in {"minimize_verification", "maximize_verification"}:
                engine.execute(Action(T.RESTORE_WINDOW, "tracked"))

        timings["full_text_to_verified_result"] = timed(
            lambda: engine.run_text("make it 1% smaller"), min(iterations, 10))

        with tempfile.TemporaryDirectory(prefix="aria-phase2-") as temporary:
            path_engine = Engine(files=InertFiles(), windows=manager)
            result_holder = []
            timings["path_launch_to_unverified_result"] = timed(
                lambda: result_holder.append(path_engine.execute(Action(T.OPEN_PATH, temporary))), iterations)
            path_engine.close()
            if any(item.verification.value != "UNVERIFIED" for item in result_holder):
                raise AssertionError("OPEN_PATH unexpectedly claimed verified UI correlation")

        startup_command = [sys.executable, "-c", "from aria.engine import Engine; e=Engine(); e.close()"]
        timings["startup"] = timed(
            lambda: subprocess.run(startup_command, check=True, capture_output=True, timeout=10),
            min(iterations, 10))

        token = uuid.uuid4().hex
        app_name = f"ARIA benchmark fixture {token}"
        programs = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs"
        shortcut = programs / f"{app_name}.lnk"
        fixture = Path(__file__).parents[1] / "tests/fixtures/window_app.py"
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        _shortcut(shortcut, pythonw, f'"{fixture}" "{app_name}"')
        deadline = time.monotonic() + 20
        while True:
            try:
                applications.resolve(app_name); break
            except LookupError:
                if time.monotonic() >= deadline: raise
                time.sleep(.5)
        launch_values = []
        for _ in range(launch_iterations):
            launch_engine = Engine(windows=manager, applications=applications)
            started = time.perf_counter_ns()
            result = launch_engine.execute(Action(T.OPEN_APPLICATION, app_name))
            launch_values.append((time.perf_counter_ns() - started) / 1_000_000)
            if result.verification.value != "VERIFIED":
                raise AssertionError("Application launch was not verified")
            handle = result.data["handle"]
            ctypes.windll.user32.PostMessageW(handle, 0x0010, 0, 0)
            _wait_gone(manager, handle); launch_engine.close()
        timings["application_launch_to_verified_window"] = launch_values
        launch_status = "VERIFIED"

        cpu_start = sum(process.cpu_times()[:2]); idle_start = time.perf_counter(); time.sleep(1)
        idle_seconds = time.perf_counter() - idle_start
        idle_cpu = sum(process.cpu_times()[:2]) - cpu_start
        virtual_screen = {"x": ctypes.windll.user32.GetSystemMetrics(76),
                          "y": ctypes.windll.user32.GetSystemMetrics(77),
                          "width": ctypes.windll.user32.GetSystemMetrics(78),
                          "height": ctypes.windll.user32.GetSystemMetrics(79)}
        return {
            "phase": 2,
            "method": "Native disposable Tk window; generated Start Menu shortcut; inert OPEN_PATH adapter. p50/p95 use linear interpolation over wall-clock milliseconds.",
            "environment": {
                "platform": platform.platform(), "windows_release": platform.release(),
                "windows_build": platform.version(), "python": platform.python_version(),
                "processor": platform.processor(), "logical_cpus": psutil.cpu_count(),
                "physical_memory_gib": psutil.virtual_memory().total / 1073741824,
                "monitor_count": ctypes.windll.user32.GetSystemMetrics(80),
                "virtual_screen": virtual_screen,
            },
            "timing_ms": {name: summary(values) for name, values in timings.items()},
            "application_launch_verification": launch_status,
            "path_launch_verification": "UNVERIFIED by contract; timing uses an inert adapter",
            "resources": {"rss_mib": process.memory_info().rss / 1048576,
                          "idle_window_seconds": idle_seconds,
                          "idle_cpu_percent_one_core": 100 * idle_cpu / idle_seconds,
                          "process_count": 1 + len(process.children(recursive=True))},
        }
    finally:
        if shortcut is not None:
            shortcut.unlink(missing_ok=True)
        root.destroy(); engine.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--launch-iterations", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(); report = measure(args.iterations, args.launch_iterations)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
