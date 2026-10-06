"""Phase 3 deterministic-language evaluation; never executes real adapters."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from aria.core import ActionType
from aria.desktop import Application, Applications
from aria.parser import ClarificationRequired, UnsupportedCommand
from scripts.phase0_eval import (ROOT, SAFE_STATE_ACTIONS, WINDOW_ACTIONS,
                                 _expected_valid, controlled_engine,
                                 evaluate_case, load_datasets, normalized,
                                 score, semantic_target, summarize)


HELD_OUT_SHA256 = "079DB847B852C13AE6AD8C7269ABA71C620D2700561C46E237843B16DF443580"
PHASE0_BASELINE = {
    "capability_accuracy": 14 / 23,
    "complete_action_accuracy": 13 / 23,
    "appropriate_abstention": 7 / 7,
    "clarification_accuracy": 2 / 4,
    "high_risk_false_proposals": 0,
}


class FixtureApplications(Applications):
    cache_seconds = 3600

    def __init__(self, names: set[str]):
        super().__init__()
        self.items = [Application(name, f"fixture.{index}")
                      for index, name in enumerate(sorted(names), 1)]

    def discover(self): return list(self.items)
    def recheck(self, application):
        matches = [item for item in self.items if item == application]
        if len(matches) != 1: raise ClarificationRequired("Application identity changed")
        return matches[0]
    def launch(self, application): return application


def _application_names(cases: list[dict]) -> set[str]:
    return {step["expected"]["target"].split(":", 1)[1]
            for case in cases for step in case["steps"]
            if step["expected"].get("action") == ActionType.OPEN_APPLICATION.value}


def load_phase3(path: Path = ROOT / "tests/data/phase3_development.json") -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data.get("split") != "phase3_development":
        raise ValueError("Invalid Phase 3 corpus header")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases: raise ValueError("Phase 3 corpus is empty")
    phase0 = load_datasets()
    ids = {case["id"] for rows in phase0.values() for case in rows}
    families = {case["family"] for rows in phase0.values() for case in rows}
    phrases = {normalized(step["text"]) for rows in phase0.values()
               for case in rows for step in case["steps"]}
    for case in cases:
        if case["id"] in ids or case["family"] in families: raise ValueError("Phase 3 corpus leakage")
        if set(case["context"]) != {"tracked_window", "foreground_window"}:
            raise ValueError("Phase 3 case needs explicit state")
        for step in case["steps"]:
            _expected_valid(step["expected"])
            phrase = normalized(step["text"])
            if phrase in phrases: raise ValueError("Phase 3 utterance duplicates Phase 0")
            phrases.add(phrase)
        ids.add(case["id"]); families.add(case["family"])
    return cases


def _outcome(exc: Exception) -> str:
    if isinstance(exc, ClarificationRequired): return "clarify"
    if isinstance(exc, UnsupportedCommand): return "abstain"
    return "clarify" if isinstance(exc, LookupError) else "abstain"


def evaluate_resolved_case(case: dict, applications: FixtureApplications) -> list[dict]:
    engine = controlled_engine(case["context"])
    engine.applications = applications
    rows = []
    try:
        for index, step in enumerate(case["steps"]):
            started = time.perf_counter_ns(); action = None; reason = None
            actual = {"outcome": "abstain"}
            try:
                action = engine.interpret(step["text"]).validate()
                if action.kind == ActionType.OPEN_APPLICATION:
                    target = f"app:{normalized(applications.resolve(action.target).name)}"
                else:
                    target = semantic_target(engine, action)
                actual = {"outcome": "action", "action": action.kind.value,
                          "target": target, "params": dict(action.params)}
            except (ValueError, LookupError) as exc:
                reason = type(exc).__name__; actual = {"outcome": _outcome(exc)}
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            if action is not None and actual["outcome"] == "action" and action.kind in SAFE_STATE_ACTIONS:
                engine.execute(action)
            row = score(step["expected"], actual)
            row.update(case_id=case["id"], step=index + 1, cohort=case["cohort"],
                       modality=case["modality"], phenomena=case["phenomena"],
                       expected=step["expected"], actual=actual, error_type=reason,
                       interpretation_ms=elapsed)
            rows.append(row)
    finally:
        engine.close()
    return rows


def breakdown(rows: list[dict], key: str) -> dict:
    values = sorted({value for row in rows for value in
                     (row[key] if isinstance(row[key], list) else [row[key]])})
    return {value: summarize([row for row in rows if value in
            (row[key] if isinstance(row[key], list) else [row[key]])]) for value in values}


def evaluate() -> dict:
    held_path = ROOT / "tests/data/phase0_held_out.json"
    digest = hashlib.sha256(held_path.read_bytes()).hexdigest().upper()
    if digest != HELD_OUT_SHA256: raise ValueError("Frozen Phase 0 held-out hash changed")
    phase0 = load_datasets(); phase3 = load_phase3()
    current_original = {}
    for split, cases in phase0.items():
        current_original[split] = summarize([row for case in cases for row in evaluate_case(case)])
    resolved_sets = {"phase3_development": phase3, "phase0_held_out": phase0["held_out"]}
    resolved = {}
    for split, cases in resolved_sets.items():
        applications = FixtureApplications(_application_names(cases))
        rows = [row for case in cases for row in evaluate_resolved_case(case, applications)]
        resolved[split] = {"summary": summarize(rows),
                           "cohorts": breakdown(rows, "cohort"),
                           "modalities": breakdown(rows, "modality"),
                           "phenomena": breakdown(rows, "phenomena"),
                           "failures": [{"case_id": row["case_id"], "step": row["step"],
                                         "expected": row["expected"], "actual": row["actual"],
                                         "error_type": row["error_type"]}
                                        for row in rows if not row["complete_correct"]]}
    return {"phase": 3, "frozen_held_out_sha256": digest,
            "phase0_historical_baseline": PHASE0_BASELINE,
            "phase0_original_method_current_interpreter": current_original,
            "resolution_aware": resolved,
            "note": "Diagnostic authored corpora; not Phase 7 or real-world accuracy."}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); result = evaluate()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
