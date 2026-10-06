"""CPU intent evaluation; actions execute only through controlled test adapters.

No application launch, browser navigation, file mutation, or user input capture.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import statistics
import time
from unittest.mock import Mock

import psutil

from aria.core import Action, ActionType, Rect, Result
from aria.engine import Engine
from aria.intent import CAPABILITIES, Interpreter, parse_output_json
from aria.local_intent import IntentConfig, LocalIntentModel
from aria.parser import parse


def wire(action):
    return {"action": action.kind.value, "target": action.target, "params": dict(action.params)}


def same(actual, expected):
    if actual is None or expected is None:
        return actual == expected
    return (actual["action"] == expected["action"] and actual["params"] == expected["params"]
            and (actual["target"] or "").casefold() == (expected["target"] or "").casefold())


def classify_output(raw):
    flags = {"schema_valid_action": False, "uncertain": False, "unsupported_action": False}
    try:
        parsed = parse_output_json(raw)
    except (ValueError, TypeError):
        return flags
    flags["uncertain"] = parsed == {"status": "uncertain"}
    if not isinstance(parsed, dict):
        return flags
    flags["unsupported_action"] = parsed.get("action") not in {None, *[k.value for k in CAPABILITIES]}
    if set(parsed) == {"action", "target", "params"}:
        try:
            Action(ActionType(parsed["action"]), parsed["target"], parsed["params"]).validate()
            flags["schema_valid_action"] = parsed["action"] in CAPABILITIES
        except (ValueError, TypeError):
            pass
    return flags


def resources():
    parent = psutil.Process()
    items = [parent, *parent.children(recursive=True)]
    return {
        "processes": len(items),
        "rss_mib": round(sum(p.memory_info().rss for p in items)/1024**2, 3),
        "cpu_seconds": sum(p.cpu_times().user + p.cpu_times().system for p in items),
    }


def idle():
    start = resources()
    begin = time.perf_counter()
    time.sleep(1)
    end = resources()
    end["cpu_percent_1s"] = round(100*(end["cpu_seconds"]-start["cpu_seconds"])/(time.perf_counter()-begin), 3)
    return end


def controlled_engine(interpreter):
    windows = Mock()
    windows.windows.return_value = []
    windows.wait_for.return_value = windows.active.return_value = windows.find.return_value = 7
    windows.exists.return_value = True
    windows.title.return_value = "Controlled benchmark window"
    windows.rect.return_value = Rect(100, 100, 1000, 800)
    windows.work_area.return_value = Rect(0, 0, 1920, 1040)
    windows.place.side_effect = lambda _handle, rect: setattr(windows.rect, "return_value", rect)
    browser = Mock()
    browser.execute.return_value = Result(True, "Controlled browser adapter")
    return Engine(windows=windows, applications=Mock(), files=Mock(), volume=Mock(),
                  shutdown=Mock(), browser_factory=lambda: browser, interpreter=interpreter)


class RecordingModel(LocalIntentModel):
    def generate(self, *args, **kwargs):
        self.raw = None
        self.raw = super().generate(*args, **kwargs)
        return self.raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path(".aria-runtime/qwen2.5-1.5b-instruct-q4_k_m.gguf"))
    parser.add_argument("--runtime", type=Path, default=Path(".aria-runtime/b11126/llama-server.exe"))
    parser.add_argument("--output", type=Path, default=Path("logs/intent-baseline.json"))
    parser.add_argument("--skip-model", action="store_true", help="Measure fast path only; never start the native runtime")
    args = parser.parse_args()
    cases = json.loads(Path("tests/data/intent_eval.json").read_text(encoding="utf-8"))
    started = time.perf_counter()
    model = RecordingModel(IntentConfig(args.model, args.runtime))
    interpreter = Interpreter(None if args.skip_model else model)
    # Real Engine construction baseline, not the controlled adapter allocation.
    baseline_engine = Engine(interpreter=interpreter)
    init_ms = (time.perf_counter()-started)*1000
    before = idle()
    fast = []
    for _ in range(1000):
        started = time.perf_counter()
        interpreter.interpret("open camera")
        fast.append((time.perf_counter()-started)*1000)
    assert model.process is None

    baseline = []
    for case in cases:
        try:
            result = wire(parse(case["text"]))
        except ValueError:
            result = None
        baseline.append({"text": case["text"], "action": result, "correct": same(result, case["expected"])})
    engine = controlled_engine(interpreter)
    results = []
    blocked = None
    loaded = None
    try:
        for case in cases:
            events = {}
            cpu_before = resources()["cpu_seconds"]
            started = time.perf_counter()
            row = {"text": case["text"], "category": case["category"], "expected": case["expected"]}
            model.raw = None
            try:
                action = engine.interpret(case["text"], on_event=lambda name: events.update({name: time.perf_counter()}))
                row["action"] = wire(action)
                row["correct"] = same(row["action"], case["expected"])
                # Only expected, validated actions reach the controlled adapters.
                if row["correct"]:
                    row["executed_controlled"] = engine.execute(action).ok
            except (ValueError, OSError) as exc:
                row.update(action=None, error=str(exc), correct=case["expected"] is None)
                if interpreter.last_route == "model" and model.raw is None:
                    blocked = str(exc)
                    row["correct"] = None
            row.update(route=interpreter.last_route, total_ms=(time.perf_counter()-started)*1000,
                       event_offsets_ms={key: (stamp-started)*1000 for key, stamp in events.items()})
            if row["route"] == "model":
                row.update(raw_output=model.raw, metrics=dict(model.last_metrics))
                row["cpu_seconds"] = resources()["cpu_seconds"]-cpu_before
                if model.raw is not None:
                    row.update(classify_output(model.raw))
                if loaded is None and model.process is not None:
                    loaded = idle()
            results.append(row)
            print(json.dumps(row), flush=True)
            if blocked:
                break
    finally:
        engine.close()
    measured = [r for r in results if r["route"] == "model" and r.get("raw_output") is not None]
    warm = [r["metrics"]["inference_ms"] for r in measured if "load_ms" not in r["metrics"]]
    summary = None
    if not blocked and not args.skip_model:
        summary = {
            "intent_accuracy": sum(r["correct"] for r in results)/len(results),
            "fallback_rate": sum(r["route"] == "model" for r in results)/len(results),
            "schema_valid_action_rate_of_model_outputs": sum(r["schema_valid_action"] for r in measured)/len(measured) if measured else None,
            "uncertain_rate_of_model_outputs": sum(r["uncertain"] for r in measured)/len(measured) if measured else None,
            "invalid_output_rate": sum(r["action"] is None and not r["uncertain"] for r in measured)/len(measured) if measured else None,
            "unsupported_action_rate": sum(r["unsupported_action"] for r in measured)/len(measured) if measured else None,
            "warm_inference_median_ms": statistics.median(warm) if warm else None,
            "cold_first_command_ms": measured[0]["total_ms"] if measured else None,
        }
    report = {
        "status": "model_not_run" if args.skip_model else ("blocked" if blocked else "measured"), "blocker": blocked,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "platform": platform.platform(), "python": platform.python_version(),
        "cpu": platform.processor(), "logical_cpus": psutil.cpu_count(),
        "model": str(args.model), "model_bytes": args.model.stat().st_size if args.model.exists() else None,
        "runtime": str(args.runtime), "quantization": "Q4_K_M", "threads": model.config.threads,
        "engine_and_interpreter_init_ms": init_ms, "before_load": before,
        "deterministic_median_ms_1000": statistics.median(fast),
        "after_model_load": loaded, "after_cleanup": resources(),
        "deterministic_parser_accuracy": sum(r["correct"] for r in baseline)/len(baseline),
        "summary": summary, "parser_baseline": baseline, "results": results,
        "method": "Fixed development corpus, not a held-out quality estimate. One CPU run; no GPU. Controlled executor adapters only. No speech/ASR accuracy claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"results", "parser_baseline"}}, indent=2))
    return 2 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
