"""Contract checks for the Phase 0 evaluator; all execution fixtures are inert."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from aria.engine import Engine
from scripts.phase0_eval import (
    ROOT, controlled_engine, evaluate_case, load_datasets, percentile, score, summarize,
)


def copy_data(tmp_path):
    source = ROOT / "tests" / "data"
    for split in ("development", "held_out"):
        shutil.copyfile(source / f"phase0_{split}.json", tmp_path / f"phase0_{split}.json")
    return tmp_path


def rewrite(path, update):
    data = json.loads(path.read_text(encoding="utf-8"))
    update(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_datasets_have_unique_cases_and_explicit_state():
    sets = load_datasets()
    assert {name: len(rows) for name, rows in sets.items()} == {
        "development": 28, "held_out": 28,
    }
    assert all(set(row["context"]) == {"tracked_window", "foreground_window"}
               for rows in sets.values() for row in rows)
    assert any(len(row["steps"]) > 1 for rows in sets.values() for row in rows)


@pytest.mark.parametrize("change", ["duplicate_id", "duplicate_phrase", "leaked_family"])
def test_integrity_rejects_duplicates_and_leakage(tmp_path, change):
    directory = copy_data(tmp_path)
    dev = directory / "phase0_development.json"
    held = directory / "phase0_held_out.json"
    if change == "duplicate_id":
        rewrite(dev, lambda data: data["cases"][1].update(id=data["cases"][0]["id"]))
    elif change == "duplicate_phrase":
        rewrite(dev, lambda data: data["cases"][1]["steps"][0].update(
            text=data["cases"][0]["steps"][0]["text"]))
    else:
        dev_family = json.loads(dev.read_text(encoding="utf-8"))["cases"][0]["family"]
        rewrite(held, lambda data: data["cases"][0].update(family=dev_family))
    with pytest.raises(ValueError):
        load_datasets(directory)


def test_invalid_annotation_is_rejected(tmp_path):
    directory = copy_data(tmp_path)
    path = directory / "phase0_held_out.json"
    rewrite(path, lambda data: data["cases"][0]["steps"][0]["expected"].update(
        action="NONEXISTENT"))
    with pytest.raises(ValueError):
        load_datasets(directory)


def test_human_asr_requires_consent_metadata(tmp_path):
    directory = copy_data(tmp_path)
    path = directory / "phase0_held_out.json"
    def mutate(data):
        case = data["cases"][24]
        assert case["modality"] == "asr_transcript"
        case["provenance"] = "human_asr"
    rewrite(path, mutate)
    with pytest.raises(ValueError, match="consent"):
        load_datasets(directory)


def test_scoring_separates_capability_target_and_parameters():
    wanted = {"outcome": "action", "action": "MOVE_WINDOW",
              "target": "window:7", "params": {"position": "left"}}
    wrong_target = {"outcome": "action", "action": "MOVE_WINDOW",
                    "target": "window:9", "params": {"position": "left"}}
    result = score(wanted, wrong_target)
    assert result["capability_correct"]
    assert not result["target_correct"]
    assert result["parameter_correct"]
    assert not result["complete_correct"]
    assert result["false_action"]

    wrong_parameter = {**wrong_target, "target": "window:7",
                       "params": {"position": "right"}}
    result = score(wanted, wrong_parameter)
    assert result["target_correct"]
    assert not result["parameter_correct"]


def test_nonaction_and_high_risk_metrics():
    abstain = {"outcome": "abstain"}
    clarify = {"outcome": "clarify"}
    assert score(abstain, clarify)["appropriate_abstention"]
    assert not score(clarify, abstain)["clarification_correct"]
    false_delete = {"outcome": "action", "action": "DELETE_PATH",
                    "target": "literal:fixture", "params": {}}
    row = score(abstain, false_delete)
    assert row["false_action"] and row["high_risk_false_proposal"]
    scored = [
        {**score(abstain, false_delete), "expected": abstain, "actual": false_delete,
         "interpretation_ms": 1.0},
        {**score(clarify, clarify), "expected": clarify, "actual": clarify,
         "interpretation_ms": 2.0},
    ]
    summary = summarize(scored)
    assert summary["false_action_rate_on_nonactions"] == 0.5
    assert summary["high_risk_false_proposals"] == 1
    assert summary["clarification_accuracy"] == 1.0
    assert summary["appropriate_abstention_rate"] == 0.5
    assert percentile([1.0, 2.0], 50) == 1.5


def test_stateful_sequence_uses_explicit_start_and_inert_adapters():
    case = next(c for c in load_datasets()["development"] if c["id"] == "dev-024")
    assert case["context"]["tracked_window"] is None
    rows = evaluate_case(case)
    assert len(rows) == 4
    assert all(row["complete_correct"] for row in rows)
    assert rows[1]["actual"]["target"] == "window:7"


def test_no_real_action_for_delete_browser_or_shutdown(tmp_path, monkeypatch):
    target = tmp_path / "still-here.txt"
    target.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(Engine, "execute",
                        lambda *_args, **_kwargs: pytest.fail("execute called"))
    context = {"tracked_window": 7, "foreground_window": 9}
    for text in (f"delete file {target}", "open browser", "shutdown"):
        case = {"id": "isolation", "family": "isolation", "phenomena": ["direct"], "cohort": "english",
                "modality": "typed", "provenance": "authored", "context": context,
                "steps": [{"text": text, "expected": {"outcome": "abstain"}}]}
        rows = evaluate_case(case)
        assert rows[0]["actual"]["outcome"] == "action"
    assert target.read_text(encoding="utf-8") == "fixture"


def test_interpreter_is_deterministic_only():
    engine = controlled_engine({"tracked_window": None, "foreground_window": 9})
    try:
        assert engine.interpreter.model is None
    finally:
        engine.close()



def test_scoring_is_deterministic_across_repeated_cases():
    case = next(c for c in load_datasets()["held_out"] if c["id"] == "hel-024")
    first = evaluate_case(case)
    second = evaluate_case(case)
    for left, right in zip(first, second, strict=True):
        assert left["actual"] == right["actual"]
        assert left["complete_correct"] == right["complete_correct"]


def test_invalid_phenomenon_tag_is_rejected(tmp_path):
    directory = copy_data(tmp_path)
    path = directory / "phase0_held_out.json"
    rewrite(path, lambda data: data["cases"][0].update(phenomena=["unknown_tag"]))
    with pytest.raises(ValueError, match="phenomenon"):
        load_datasets(directory)
