"""No live microphone or real OS action is used by these tests."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from aria.voice import Transcript, VoiceError
from scripts import phase6_live_voice_trials as live


def test_direct_cli_help_never_opens_microphone():
    script = Path(live.__file__)
    result = subprocess.run([sys.executable, str(script), "--help"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "--consented-live" in result.stdout


def case(*, kind="intended", expected=None):
    return {"id": "trial-1", "family": "open-app", "speaker_id": "speaker-1",
            "cohort": "indian_english", "condition": "quiet", "microphone": "built-in",
            "speaking_rate": "normal", "tags": ["application"], "kind": kind,
            "reference_text": "Open Camera" if kind == "intended" else "",
            "expected": expected or ({"outcome": "action", "action": "OPEN_APPLICATION",
                                     "target": "Camera", "params": {}} if kind == "intended"
                                    else {"outcome": "abstain"}),
            "consent_record": "C:\\private\\consent.txt", "split": "development"}


def test_live_plan_requires_consent_and_separate_speakers(tmp_path, monkeypatch):
    consent = tmp_path / "consent.txt"
    consent.write_text("test-only", encoding="utf-8")
    first = case()
    first.pop("split")
    first["consent_record"] = str(consent.resolve())
    plan1, plan2 = tmp_path / "development.json", tmp_path / "held-out.json"
    plan1.write_text(json.dumps({"version": 1, "source": "human_live",
                                 "split": "development", "cases": [first]}), encoding="utf-8")
    second = {**first, "id": "trial-2"}
    plan2.write_text(json.dumps({"version": 1, "source": "human_live",
                                 "split": "held_out", "cases": [second]}), encoding="utf-8")
    monkeypatch.setattr(live, "_outside_repo", lambda _path: True)
    with pytest.raises(ValueError, match="leaks across splits"):
        live.load_plans([plan1, plan2])
    second["speaker_id"] = "speaker-2"
    plan2.write_text(json.dumps({"version": 1, "source": "human_live",
                                 "split": "held_out", "cases": [second]}), encoding="utf-8")
    with pytest.raises(ValueError, match="phrasing family leaks"):
        live.load_plans([plan1, plan2])
    second["family"] = "different-family"
    plan2.write_text(json.dumps({"version": 1, "source": "human_live",
                                 "split": "held_out", "cases": [second]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Reference utterance leaks"):
        live.load_plans([plan1, plan2])
    consent.unlink()
    with pytest.raises(ValueError, match="Consent record"):
        live.load_plans([plan1])


def test_intended_live_plan_requires_reference_words(tmp_path, monkeypatch):
    consent = tmp_path / "consent.txt"
    consent.write_text("test-only", encoding="utf-8")
    trial = case()
    trial.pop("split")
    trial["reference_text"] = "..."
    trial["consent_record"] = str(consent.resolve())
    plan = tmp_path / "development.json"
    plan.write_text(json.dumps({"version": 1, "source": "human_live",
                                "split": "development", "cases": [trial]}), encoding="utf-8")
    monkeypatch.setattr(live, "_outside_repo", lambda _path: True)
    with pytest.raises(ValueError, match="audible reference words"):
        live.load_plans([plan])


def test_prepare_only_live_trial_never_executes_or_retains_audio():
    class FakeMicrophone(live.ObservedMicrophone):
        def _capture(self, on_event=None):
            on_event("microphone_requested")
            on_event("microphone_ready")
            on_event("speech_end")
            return np.full(1600, .05, dtype=np.float32)
    class FakeASR:
        def transcribe(self, _audio): return Transcript("Open Camera", .9, "en", .99)
    microphone = FakeMicrophone()
    engine = live.InterpretOnly()
    asr = live.ObservedASR(FakeASR())
    row = live.evaluate_trial(case(), microphone, asr, engine)
    assert row["complete"] and row["audio_frames_in_memory"] == 1600
    assert row["speech_end_to_final_ms"] is not None
    assert microphone.audio is None
    assert asr.transcript is None
    assert "Open Camera" not in json.dumps(row)
    with pytest.raises(AssertionError, match="never execute"):
        engine.execute(None)
    with pytest.raises(AssertionError, match="never confirm"):
        engine.confirm(None)


def test_negative_trial_denominator_uses_triggered_trials():
    class SilentMicrophone(live.ObservedMicrophone):
        def _capture(self, on_event=None):
            on_event("microphone_requested")
            on_event("microphone_ready")
            on_event("speech_end")
            raise VoiceError("No speech detected")
    class ForbiddenASR:
        def transcribe(self, _audio): raise AssertionError("ASR should not run")
    row = live.evaluate_trial(case(kind="negative"), SilentMicrophone(),
                              live.ObservedASR(ForbiddenASR()), live.InterpretOnly())
    summary = live.summarize_live([row])
    assert row["error_type"] == "no_speech_detected"
    assert summary["negative_triggered_trials"] == 1
    assert summary["negative_command_proposal_rate"] == 0
    assert summary["missed_complete_command_rate"] is None
    assert summary["capability_accuracy"] is None


def test_live_wer_excludes_empty_reference_insertions():
    intended = {"kind": "intended", "expected_action": True,
                "reference_words": 2, "word_errors": 0, "capability": True,
                "target": True, "arguments": True, "complete": True,
                "false_action": False, "negative_command_proposal": False,
                "missed_complete_command": False, "speech_end_to_final_ms": None}
    empty_reference = {**intended, "expected_action": False,
                       "reference_words": 0, "word_errors": 2}
    assert live.summarize_live([intended, empty_reference])["wer_intended_trials"] == 0
    assert live.summarize_live([empty_reference])["wer_intended_trials"] is None


def test_live_summaries_keep_development_and_held_out_separate():
    base = {"split": "development", "cohort": "english", "kind": "intended",
            "expected_action": True, "reference_words": 2, "word_errors": 0,
            "capability": True, "target": True, "arguments": True, "complete": True,
            "false_action": False, "negative_command_proposal": False,
            "missed_complete_command": False, "speech_end_to_final_ms": 100}
    held_out = {**base, "split": "held_out", "word_errors": 2,
                "complete": False, "missed_complete_command": True}
    summaries = live.summarize_by_split([base, held_out])
    assert set(summaries) == {"development", "held_out"}
    assert summaries["development"]["overall"]["trials"] == 1
    assert summaries["held_out"]["overall"]["trials"] == 1
    assert summaries["development"]["by_cohort"]["english"]["wer_intended_trials"] == 0
    assert summaries["held_out"]["by_cohort"]["english"]["wer_intended_trials"] == 1
