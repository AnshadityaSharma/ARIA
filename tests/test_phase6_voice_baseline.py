"""Baseline harness tests; no model, microphone, or OS action is used."""
import hashlib
import json
import sys

import numpy as np
import pytest

from scripts import phase6_voice_baseline as baseline
from aria.voice import Transcript, VoiceError


def manifest(tmp_path, *, source="synthetic", split="smoke", expected=None,
             reference="Open Camera", audio_bytes=b"fixture"):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(audio_bytes)
    case = {"id": "clip-1", "family": "open-camera", "speaker_id": "synthetic",
            "cohort": "english", "condition": "clean", "microphone": "synthesized",
            "speaking_rate": "normal", "tags": ["application"],
            "audio_path": str(audio), "audio_sha256": hashlib.sha256(audio_bytes).hexdigest(),
            "reference_text": reference,
            "expected": expected or {"outcome": "action", "action": "OPEN_APPLICATION",
                                     "target": "camera", "params": {}},
            "consent_record": None}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": 1, "source": source,
                                "split": split, "cases": [case]}), encoding="utf-8")
    return path


def test_word_errors_and_zero_denominator():
    assert baseline.word_errors("Open Camera", "open camera") == (0, 2)
    assert baseline.word_errors("open Camera now", "open Camera") == (1, 3)
    assert baseline.word_errors("", "hallucinated") == (1, 0)
    assert baseline.summarize([])["wer"] is None
    assert baseline.summarize([])["false_action_rate_all_clips"] is None


def test_replay_wer_excludes_empty_reference_negative_insertions():
    positive = {"expected_action": True, "capability": True, "target": True,
                "arguments": True, "complete": True, "false_action": False,
                "missed_action": False, "word_errors": 0, "reference_words": 2,
                "asr_ms": 1, "decode_ms": 1, "parse_ms": 1}
    negative = {**positive, "expected_action": False, "word_errors": 3,
                "reference_words": 0, "false_action": True}
    assert baseline.summarize([positive, negative])["wer"] == 0
    assert baseline.summarize([negative])["wer"] is None


def test_manifest_rejects_changed_audio_and_human_manifest_in_repo(tmp_path):
    path = manifest(tmp_path)
    assert len(baseline.load_manifests([path])) == 1
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        baseline.load_manifests([path])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["source"], data["split"] = "human", "development"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="outside the repository"):
        baseline.load_manifests([path])


def test_manifest_rejects_expected_action_without_reference_words(tmp_path):
    path = manifest(tmp_path, reference="... ")
    with pytest.raises(ValueError, match="audible reference words"):
        baseline.load_manifests([path])


def test_manifest_rejects_speaker_leakage_across_splits(tmp_path, monkeypatch):
    first_dir, second_dir = tmp_path / "one", tmp_path / "two"
    first_dir.mkdir(); second_dir.mkdir()
    first = manifest(first_dir)
    second = manifest(second_dir)
    consent = tmp_path / "consent.txt"
    consent.write_text("test fixture", encoding="utf-8")
    for path, split in ((first, "development"), (second, "held_out")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["split"], data["source"] = split, "human"
        data["cases"][0]["id"] = f"{split}-1"
        data["cases"][0]["consent_record"] = str(consent.resolve())
        path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(baseline, "_outside_repo", lambda _path: True)
    with pytest.raises(ValueError, match="leaks across splits"):
        baseline.load_manifests([first, second])
    second_data = json.loads(second.read_text(encoding="utf-8"))
    second_data["cases"][0]["speaker_id"] = "another-speaker"
    second.write_text(json.dumps(second_data), encoding="utf-8")
    with pytest.raises(ValueError, match="phrasing family leaks"):
        baseline.load_manifests([first, second])
    second_data["cases"][0]["family"] = "another-family"
    second.write_text(json.dumps(second_data), encoding="utf-8")
    with pytest.raises(ValueError, match="Reference utterance leaks"):
        baseline.load_manifests([first, second])


def test_execution_free_replay_reports_metrics_without_transcripts(tmp_path, monkeypatch):
    path = manifest(tmp_path)
    class FakeASR:
        def transcribe(self, _audio): return Transcript("Open Camera", .9, "en", .99)
    monkeypatch.setattr(baseline, "LocalASR", FakeASR)
    monkeypatch.setattr("faster_whisper.decode_audio", lambda _path: np.zeros(1600, dtype=np.float32))
    report = baseline.run([path])
    assert report["summaries"]["synthetic"]["smoke"]["wer"] == 0
    assert report["summaries"]["synthetic"]["smoke"]["complete_outcome_accuracy"] == 1
    assert report["rows"][0]["error_boundary"] == "none"
    assert "Open Camera" not in json.dumps(report)
    assert report["resources"]["child_processes_after"] >= 0


def test_empty_transcription_is_scored_without_execution(tmp_path, monkeypatch):
    path = manifest(tmp_path, reference="", expected={"outcome": "abstain"})
    class FakeASR:
        def transcribe(self, _audio): raise VoiceError("No command was transcribed")
    monkeypatch.setattr(baseline, "LocalASR", FakeASR)
    monkeypatch.setattr("faster_whisper.decode_audio", lambda _path: np.zeros(1600, dtype=np.float32))
    report = baseline.run([path])
    assert report["summaries"]["synthetic"]["smoke"]["complete_outcome_accuracy"] == 1
    assert report["summaries"]["synthetic"]["smoke"]["wer"] is None
    assert report["rows"][0]["asr_error"] == "empty_transcript"


def test_score_denominators_and_false_action():
    expected = {"outcome": "action", "action": "OPEN_APPLICATION", "target": "camera", "params": {}}
    wrong = {"outcome": "action", "action": "OPEN_APPLICATION", "target": "calendar", "params": {}}
    result = baseline.score(expected, wrong)
    assert result["capability"] and not result["target"] and result["false_action"]
    assert baseline.score({"outcome": "abstain"}, wrong)["false_action"]


def test_human_summaries_never_pool_development_and_held_out():
    base = {"source": "human", "split": "development", "expected_action": True,
            "capability": True, "target": True, "arguments": True, "complete": True,
            "false_action": False, "missed_action": False, "word_errors": 0,
            "reference_words": 2, "asr_ms": 100, "decode_ms": 1, "parse_ms": 1}
    held_out = {**base, "split": "held_out", "complete": False,
                "word_errors": 2, "missed_action": True}
    summaries = baseline.summarize_by_split([base, held_out])
    assert set(summaries["human"]) == {"development", "held_out"}
    assert summaries["human"]["development"]["wer"] == 0
    assert summaries["human"]["held_out"]["wer"] == 1
    assert summaries["human"]["development"]["clips"] == 1
    assert summaries["human"]["held_out"]["clips"] == 1


def test_replay_cohort_summaries_are_separate_within_each_split():
    base = {"source": "human", "split": "development", "cohort": "english",
            "expected_action": True, "capability": True, "target": True,
            "arguments": True, "complete": True, "false_action": False,
            "missed_action": False, "word_errors": 0, "reference_words": 2,
            "asr_ms": 1, "decode_ms": 1, "parse_ms": 1}
    groups = baseline.summarize_by_cohort([
        base, {**base, "cohort": "hinglish", "word_errors": 2},
        {**base, "split": "held_out", "word_errors": 1},
    ])
    assert groups["human"]["development"]["english"]["wer"] == 0
    assert groups["human"]["development"]["hinglish"]["wer"] == 1
    assert groups["human"]["held_out"]["english"]["wer"] == .5


def test_human_report_cannot_be_written_inside_repo(monkeypatch):
    monkeypatch.setattr(baseline, "run", lambda _paths: {"summaries": {"human": {"development": {"clips": 1}}}})
    destination = baseline.ROOT / ".phase6-test-private-report-never-created.json"
    monkeypatch.setattr(sys, "argv", ["phase6_voice_baseline.py", "--manifest", "fixture.json",
                                  "--output", str(destination)])
    with pytest.raises(SystemExit) as error:
        baseline.main()
    assert error.value.code == 2
    assert not destination.exists()


def test_synthetic_report_does_not_overwrite_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(baseline, "run", lambda _paths: {"summaries": {"synthetic": {"smoke": {"clips": 1}}}})
    destination = tmp_path / "report.json"
    destination.write_text("existing", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["phase6_voice_baseline.py", "--manifest", "fixture.json",
                                  "--output", str(destination)])
    with pytest.raises(SystemExit) as error:
        baseline.main()
    assert error.value.code == 2
    assert destination.read_text(encoding="utf-8") == "existing"
