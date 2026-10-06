"""Phase 0 deterministic command evaluation. No real computer actions or model loading."""
from __future__ import annotations

import argparse
import json
import platform
import re
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import psutil

from aria.core import Action, ActionType, RISK, Rect, WindowState
from aria.desktop import Application
from aria.windows import Placement, Window, WindowIdentity
from aria.engine import Engine
from aria.intent import Interpreter
from aria.parser import ClarificationRequired, UnsupportedCommand

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ("development", "held_out")
COHORTS = {"english", "indian_english", "hinglish"}
MODALITIES = {"typed", "asr_transcript"}
PHENOMENA = {"direct", "paraphrase", "natural_phrasing", "code_switching", "ambiguous", "unsupported", "high_risk_negative", "compound", "stateful", "missing_context", "asr_error", "literal_payload"}
OUTCOMES = {"action", "clarify", "abstain"}
WINDOW_ACTIONS = {
    ActionType.FOCUS_WINDOW, ActionType.MINIMIZE_WINDOW, ActionType.MAXIMIZE_WINDOW,
    ActionType.RESTORE_WINDOW, ActionType.MOVE_WINDOW, ActionType.RESIZE_WINDOW,
}
SAFE_STATE_ACTIONS = WINDOW_ACTIONS | {ActionType.OPEN_APPLICATION}


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * percent / 100
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _expected_valid(expected: dict) -> None:
    if not isinstance(expected, dict) or expected.get("outcome") not in OUTCOMES:
        raise ValueError("Expected outcome must be action, clarify, or abstain")
    if expected["outcome"] == "action":
        if set(expected) != {"outcome", "action", "target", "params"}:
            raise ValueError("Action expectation requires exactly action, target, params")
        kind = ActionType(expected["action"])
        target = expected["target"]
        params = expected["params"]
        if kind in WINDOW_ACTIONS:
            if not isinstance(target, str) or not re.fullmatch(r"window:\d+", target):
                raise ValueError("Window expectation needs resolved window:N target")
            Action(kind, "tracked", params).validate()
        else:
            if not isinstance(target, str) or not target:
                raise ValueError("Expected semantic target is required")
            validation_target = None if target == "none" else target.removeprefix("app:").removeprefix("literal:")
            Action(kind, validation_target, params).validate()
    elif set(expected) != {"outcome"}:
        raise ValueError("Non-action expectation cannot carry an action")


def load_datasets(directory: Path = ROOT / "tests" / "data") -> dict:
    datasets = {}
    ids, families, utterances = set(), {}, {}
    for split in SPLITS:
        path = directory / f"phase0_{split}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if set(data) != {"version", "split", "cases"} or data["version"] != 1 or data["split"] != split:
            raise ValueError(f"Invalid dataset header: {path}")
        if not isinstance(data["cases"], list) or not data["cases"]:
            raise ValueError(f"Empty dataset: {path}")
        for case in data["cases"]:
            required_case_fields = {"id", "family", "cohort", "modality", "provenance", "context", "steps", "phenomena"}
            if not required_case_fields <= set(case) or set(case) - required_case_fields - {"voice"}:
                raise ValueError("Case fields must match the version 1 contract")
            case_id, family = case["id"], case["family"]
            if not isinstance(case_id, str) or not case_id.startswith(split[:3] + "-") or case_id in ids:
                raise ValueError(f"Duplicate or invalid case ID: {case_id}")
            if not isinstance(family, str) or not family:
                raise ValueError("Missing phrasing family")
            if family in families and families[family] != split:
                raise ValueError(f"Family leaks across splits: {family}")
            if not isinstance(case["phenomena"], list) or not case["phenomena"] or len(case["phenomena"]) != len(set(case["phenomena"])) or not set(case["phenomena"]) <= PHENOMENA:
                raise ValueError("Invalid phenomenon tags")
            if case["cohort"] not in COHORTS or case["modality"] not in MODALITIES:
                raise ValueError("Invalid cohort or modality")
            if case["provenance"] not in {"authored", "simulated_asr", "human_asr"}:
                raise ValueError("Invalid provenance")
            if (case["modality"] == "typed") != (case["provenance"] == "authored"):
                raise ValueError("Typed/authored and ASR provenance must agree")
            if case["provenance"] == "human_asr":
                voice = case.get("voice")
                if not isinstance(voice, dict) or set(voice) != {"speaker_id", "consent_record", "audio_sha256", "asr_configuration", "audio_duration_ms"}:
                    raise ValueError("Human ASR needs complete local consent/provenance metadata")
                if not all(isinstance(voice[k], str) and voice[k] for k in ("speaker_id", "consent_record", "audio_sha256", "asr_configuration")):
                    raise ValueError("Invalid human ASR provenance")
                if type(voice["audio_duration_ms"]) is not int or voice["audio_duration_ms"] <= 0:
                    raise ValueError("Invalid audio duration")
            elif "voice" in case:
                raise ValueError("Only human ASR cases may include voice provenance")
            context = case["context"]
            if not isinstance(context, dict) or set(context) != {"tracked_window", "foreground_window"}:
                raise ValueError("Context needs explicit tracked and foreground window IDs")
            if not all(v is None or type(v) is int and v > 0 for v in context.values()):
                raise ValueError("Invalid window fixture ID")
            if not isinstance(case["steps"], list) or not case["steps"]:
                raise ValueError("Case must have one or more steps")
            for step in case["steps"]:
                if set(step) != {"text", "expected"} or not isinstance(step["text"], str) or not step["text"].strip():
                    raise ValueError("Invalid step")
                _expected_valid(step["expected"])
                phrase = normalized(step["text"])
                if phrase in utterances:
                    raise ValueError(f"Utterance leaks across splits: {phrase}")
                utterances[phrase] = split
            ids.add(case_id)
            families[family] = split
        datasets[split] = data["cases"]
    return datasets


class Forbidden:
    def __getattr__(self, name):
        raise AssertionError(f"Forbidden real adapter access: {name}")


class SafeWindows:
    def __init__(self, tracked: int | None, foreground: int | None):
        self.foreground = foreground
        self.rectangles = {n: Rect(100, 100, 1000, 800) for n in (tracked, foreground, 7) if n is not None}

    def windows(self):
        return [self.snapshot(handle) for handle in self.rectangles]
    def snapshot(self, handle):
        if handle not in self.rectangles: raise LookupError("Window is unavailable")
        return Window(handle, self.title(handle), self.rect(handle), handle * 10,
                      WindowIdentity(handle, handle * 10, handle * 100),
                      f"fixture-{handle}.exe", f"fixture.window.{handle}", Placement.NORMAL)
    def wait_for(self, *_):
        return 7
    def exists(self, handle):
        return handle in self.rectangles
    def active(self):
        if self.foreground is None:
            raise LookupError("No foreground window")
        return self.foreground
    def active_window(self):
        return self.snapshot(self.active())
    def find(self, title):
        raise LookupError(f"Window is not in the controlled fixture: {title}")
    def resolve(self, title):
        raise LookupError(f"Window is not in the controlled fixture: {title}")
    def recheck(self, target):
        identity = target.identity if isinstance(target, Window) else target
        current = self.snapshot(identity.handle)
        if current.identity != identity: raise LookupError("Window identity changed")
        return current
    def rect(self, handle):
        return self.rectangles[handle]
    def title(self, handle):
        return f"Fixture window {handle}"
    def work_area(self, _handle):
        return Rect(0, 0, 1920, 1040)
    def place(self, handle, rect):
        handle = self.recheck(handle).handle if isinstance(handle, Window) else handle
        self.rectangles[handle] = rect
        return self.snapshot(handle)
    def focus(self, _handle):
        return self.recheck(_handle)
    def show(self, _handle, _mode):
        return self.recheck(_handle)
    def wait_for_application(self, *_args):
        self.rectangles.setdefault(7, Rect(100, 100, 1000, 800))
        return self.snapshot(7)


class SafeApplications:
    def resolve(self, name): return Application(name, f"fixture.{name.casefold()}")
    def recheck(self, application): return application
    def launch(self, application): return application


def controlled_engine(context: dict) -> Engine:
    windows = SafeWindows(context["tracked_window"], context["foreground_window"])
    engine = Engine(
        windows=windows, applications=SafeApplications(), files=Forbidden(),
        volume=Forbidden(), shutdown=lambda: (_ for _ in ()).throw(AssertionError("shutdown")),
        browser_factory=lambda: (_ for _ in ()).throw(AssertionError("browser")),
        interpreter=Interpreter(),
    )
    engine.activation_window = context["foreground_window"]
    tracked = context["tracked_window"]
    if tracked is not None:
        engine.state = WindowState(
            handle=tracked, title=windows.title(tracked), geometry=windows.rect(tracked)
        )
    return engine


def error_outcome(exc: Exception) -> str:
    if isinstance(exc, ClarificationRequired):
        return "clarify"
    if isinstance(exc, UnsupportedCommand):
        return "abstain"
    # Compatibility for older adapter errors retained by the Phase 0 runner.
    message = str(exc).casefold()
    if isinstance(exc, LookupError) or message.startswith("name the application"):
        return "clarify"
    return "abstain"


def semantic_target(engine: Engine, action: Action) -> str:
    if action.kind in WINDOW_ACTIONS:
        target = engine._handle(action.target)
        return f"window:{target.handle if isinstance(target, Window) else target}"
    if action.target is None:
        return "none"
    if action.kind == ActionType.OPEN_APPLICATION:
        return f"app:{normalized(action.target or '')}"
    return f"literal:{normalized(action.target or '')}"


def evaluate_case(case: dict) -> list[dict]:
    engine = controlled_engine(case["context"])
    rows = []
    try:
        for index, step in enumerate(case["steps"]):
            expected = step["expected"]
            start = time.perf_counter_ns()
            action = None
            actual = {"outcome": "abstain"}
            reason = None
            try:
                action = engine.interpret(step["text"]).validate()
                target = semantic_target(engine, action)
                actual = {
                    "outcome": "action", "action": action.kind.value,
                    "target": target, "params": dict(action.params),
                }
            except (ValueError, LookupError) as exc:
                reason = type(exc).__name__
                actual = {"outcome": error_outcome(exc)}
            elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
            # Only fake window/application operations advance sequence state.
            # Every other action is a proposal only; no file/browser/system adapter runs.
            if action is not None and actual["outcome"] == "action" and action.kind in SAFE_STATE_ACTIONS:
                engine.execute(action)
            row = score(expected, actual)
            row.update(
                case_id=case["id"], step=index + 1, cohort=case["cohort"],
                modality=case["modality"], provenance=case["provenance"],
                family=case["family"], phenomena=case["phenomena"], expected=expected, actual=actual,
                error_type=reason, interpretation_ms=elapsed_ms,
            )
            rows.append(row)
    finally:
        engine.close()
    return rows


def score(expected: dict, actual: dict) -> dict:
    wanted_action = expected["outcome"] == "action"
    got_action = actual["outcome"] == "action"
    capability_correct = wanted_action and got_action and expected["action"] == actual["action"]
    target_correct = capability_correct and expected["target"].casefold() == actual["target"].casefold()
    parameter_correct = capability_correct and expected["params"] == actual["params"]
    complete = (
        capability_correct and target_correct and parameter_correct
        if wanted_action else expected["outcome"] == actual["outcome"]
    )
    false_action = got_action and not complete
    high_risk_false = false_action and RISK[ActionType(actual["action"])].value == "HIGH"
    return {
        "complete_correct": complete,
        "capability_correct": capability_correct,
        "target_correct": target_correct,
        "parameter_correct": parameter_correct,
        "appropriate_abstention": not wanted_action and not got_action,
        "clarification_correct": expected["outcome"] == actual["outcome"] == "clarify",
        "false_action": false_action,
        "high_risk_false_proposal": high_risk_false,
    }


def summarize(rows: list[dict]) -> dict:
    action_rows = [r for r in rows if r["expected"]["outcome"] == "action"]
    nonaction_rows = [r for r in rows if r["expected"]["outcome"] != "action"]
    matched_capability = [r for r in action_rows if r["capability_correct"]]
    clarification_rows = [r for r in rows if r["expected"]["outcome"] == "clarify"]
    times = [r["interpretation_ms"] for r in rows]
    def fraction(numerator, denominator):
        return numerator / denominator if denominator else None
    return {
        "steps": len(rows),
        "expected_action": len(action_rows),
        "expected_nonaction": len(nonaction_rows),
        "complete_outcome_accuracy_all_steps": fraction(sum(r["complete_correct"] for r in rows), len(rows)),
        "complete_action_accuracy": fraction(sum(r["complete_correct"] for r in action_rows), len(action_rows)),
        "capability_accuracy": fraction(sum(r["capability_correct"] for r in action_rows), len(action_rows)),
        "target_accuracy_given_capability": fraction(sum(r["target_correct"] for r in matched_capability), len(matched_capability)),
        "parameter_accuracy_given_capability": fraction(sum(r["parameter_correct"] for r in matched_capability), len(matched_capability)),
        "appropriate_abstention_rate": fraction(sum(r["appropriate_abstention"] for r in nonaction_rows), len(nonaction_rows)),
        "abstention_rate_all_steps": fraction(sum(r["actual"]["outcome"] == "abstain" for r in rows), len(rows)),
        "clarification_rate_all_steps": fraction(sum(r["actual"]["outcome"] == "clarify" for r in rows), len(rows)),
        "clarification_accuracy": fraction(sum(r["clarification_correct"] for r in clarification_rows), len(clarification_rows)),
        "false_action_rate_all_steps": fraction(sum(r["false_action"] for r in rows), len(rows)),
        "false_action_rate_on_nonactions": fraction(sum(r["false_action"] for r in nonaction_rows), len(nonaction_rows)),
        "high_risk_false_proposals": sum(r["high_risk_false_proposal"] for r in rows),
        "high_risk_false_proposal_rate_all_steps": fraction(sum(r["high_risk_false_proposal"] for r in rows), len(rows)),
        "interpretation_p50_ms": percentile(times, 50),
        "interpretation_p95_ms": percentile(times, 95),
    }


def tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file() and "__pycache__" not in item.parts)


def resources_and_speed(iterations: int) -> dict:
    if iterations < 20:
        raise ValueError("At least 20 warm iterations are required")
    process = psutil.Process()
    start_cpu = sum(process.cpu_times()[:2])
    start = time.perf_counter()
    time.sleep(1)
    idle_seconds = time.perf_counter() - start
    idle_cpu = sum(process.cpu_times()[:2]) - start_cpu
    interpreter = Interpreter()
    # Warm up the same deterministic path before sampling.
    for _ in range(20):
        interpreter.interpret("open camera")
    samples = []
    for _ in range(iterations):
        tick = time.perf_counter_ns()
        interpreter.interpret("open camera")
        samples.append((time.perf_counter_ns() - tick) / 1_000_000)
    interpreter.close()
    startups = []
    for _ in range(5):
        tick = time.perf_counter_ns()
        subprocess.run([sys.executable, "-c", "from aria.intent import Interpreter; Interpreter()"], check=True, capture_output=True, timeout=10, cwd=ROOT)
        startups.append((time.perf_counter_ns() - tick) / 1_000_000)
    return {
        "fresh_process_startup_samples_ms": startups,
        "fresh_process_startup_p50_ms": percentile(startups, 50),
        "fresh_process_startup_p95_ms": percentile(startups, 95),
        "warm_iterations": iterations,
        "warm_text": "open camera",
        "warm_interpretation_p50_ms": percentile(samples, 50),
        "warm_interpretation_p95_ms": percentile(samples, 95),
        "idle_window_seconds": idle_seconds,
        "idle_cpu_percent_one_core": 100 * idle_cpu / idle_seconds,
        "rss_mib": process.memory_info().rss / 1048576,
        "process_count": 1 + len(process.children(recursive=True)),
        "source_tree_bytes": tree_bytes(ROOT / "src" / "aria"),
        "venv_bytes": tree_bytes(ROOT / ".venv") if (ROOT / ".venv").exists() else None,
        "installed_package_bytes": None,
        "installed_size_note": "No distributable installer exists; source-tree bytes are not installed size.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "logs" / "phase0-baseline.json")
    parser.add_argument("--iterations", type=int, default=1000)
    args = parser.parse_args()
    datasets = load_datasets()
    rows_by_split = {
        split: [row for case in datasets[split] for row in evaluate_case(case)]
        for split in SPLITS
    }
    report = {
        "schema_version": 1,
        "phase": 0,
        "status": "baseline_only_not_phase7_acceptance",
        "environment": {
            "platform": platform.platform(), "python": platform.python_version(),
            "processor": platform.processor(), "logical_cpus": psutil.cpu_count(),
        },
        "case_counts": {split: len(datasets[split]) for split in SPLITS},
        "cohorts": {split: dict(Counter(c["cohort"] for c in datasets[split])) for split in SPLITS},
        "modalities": {split: dict(Counter(c["modality"] for c in datasets[split])) for split in SPLITS},
        "summary": {split: summarize(rows) for split, rows in rows_by_split.items()},
        "by_cohort": {
            split: {cohort: summarize([r for r in rows if r["cohort"] == cohort])
                    for cohort in sorted({r["cohort"] for r in rows})}
            for split, rows in rows_by_split.items()
        },
        "by_modality": {
            split: {modality: summarize([r for r in rows if r["modality"] == modality])
                    for modality in sorted({r["modality"] for r in rows})}
            for split, rows in rows_by_split.items()
        },
        "by_phenomenon": {
            split: {tag: summarize([r for r in rows if tag in r["phenomena"]])
                    for tag in sorted({tag for r in rows for tag in r["phenomena"]})}
            for split, rows in rows_by_split.items()
        },
        "performance": resources_and_speed(args.iterations),
        "method": "Deterministic Interpreter only; controlled Windows/app fixtures; no real actions; ASR-like transcripts are simulated text; no live speech, execution-success, or Phase 7 gate claim.",
        "rows": rows_by_split,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
