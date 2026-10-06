import hashlib
from pathlib import Path

from scripts.phase3_eval import (HELD_OUT_SHA256, FixtureApplications,
                                 _application_names, evaluate_resolved_case,
                                 load_phase3)


def test_phase3_development_corpus_is_valid_and_separate():
    cases = load_phase3()
    assert len(cases) == 20
    assert len({case["id"] for case in cases}) == len(cases)


def test_phase3_development_expected_outcomes_pass():
    cases = load_phase3(); applications = FixtureApplications(_application_names(cases))
    rows = [row for case in cases for row in evaluate_resolved_case(case, applications)]
    assert len(rows) == 22
    assert all(row["complete_correct"] for row in rows)
    assert not any(row["false_action"] or row["high_risk_false_proposal"] for row in rows)


def test_phase0_held_out_hash_is_unchanged():
    digest = hashlib.sha256(Path("tests/data/phase0_held_out.json").read_bytes()).hexdigest().upper()
    assert digest == HELD_OUT_SHA256
