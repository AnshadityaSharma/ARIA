"""Opt-in live voice evaluation. Never calls Engine.execute or stores raw audio/text."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from pathlib import Path

import numpy as np
import psutil

from aria.core import Action, ActionType
from aria.intent import Interpreter
from aria.parser import ClarificationRequired
from aria.voice import (LocalASR, LowConfidence, Microphone, Timeline,
                        VoiceController, VoiceError)
if __package__:
    from scripts.phase6_voice_baseline import COHORTS, CONFIG, ROOT, _outside_repo, percentile, score, word_errors, words
else:
    from phase6_voice_baseline import COHORTS, CONFIG, ROOT, _outside_repo, percentile, score, word_errors, words

FIELDS = {"id", "family", "speaker_id", "cohort", "condition", "microphone",
          "speaking_rate", "tags", "kind", "reference_text", "expected", "consent_record"}


def load_plans(paths: list[Path]) -> list[dict]:
    cases, ids, speakers, families, utterances = [], set(), {}, {}, {}
    for path in paths:
        if not path.is_absolute() or not _outside_repo(path):
            raise ValueError("Live plan must be an absolute path outside the repository")
        data = json.loads(path.read_text(encoding="utf-8"))
        if (set(data) != {"version", "source", "split", "cases"}
                or data["version"] != 1 or data["source"] != "human_live"
                or data["split"] not in {"development", "held_out"}
                or not isinstance(data["cases"], list) or not data["cases"]):
            raise ValueError("Invalid live plan header")
        split = data["split"]
        for case in data["cases"]:
            if not isinstance(case, dict) or set(case) != FIELDS:
                raise ValueError("Invalid live trial fields")
            if not all(isinstance(case[key], str) and case[key].strip() for key in
                       ("id", "family", "speaker_id", "cohort", "condition",
                        "microphone", "speaking_rate", "kind", "consent_record")):
                raise ValueError("Missing live trial metadata")
            if (case["id"] in ids or case["cohort"] not in COHORTS
                    or case["kind"] not in {"intended", "negative"}
                    or not isinstance(case["reference_text"], str)):
                raise ValueError("Invalid live trial ID, cohort, kind, or reference")
            ids.add(case["id"])
            consent = Path(case["consent_record"])
            if not consent.is_absolute() or not _outside_repo(consent) or not consent.is_file():
                raise ValueError("Consent record must exist outside the repository")
            if (not isinstance(case["tags"], list) or not case["tags"]
                    or not all(isinstance(tag, str) and tag for tag in case["tags"])):
                raise ValueError("Live trial needs tags")
            expected = case["expected"]
            if not isinstance(expected, dict) or expected.get("outcome") not in {"action", "clarify", "abstain"}:
                raise ValueError("Invalid expected outcome")
            if case["kind"] == "intended" and not words(case["reference_text"]):
                raise ValueError("Intended trial needs audible reference words")
            if expected["outcome"] == "action":
                if set(expected) != {"outcome", "action", "target", "params"}:
                    raise ValueError("Invalid action expectation")
                Action(ActionType(expected["action"]), expected["target"], expected["params"]).validate()
            elif set(expected) != {"outcome"}:
                raise ValueError("Invalid non-action expectation")
            if case["kind"] == "negative" and expected["outcome"] != "abstain":
                raise ValueError("Negative trial must expect abstention")
            for mapping, value in ((speakers, case["speaker_id"]), (families, case["family"])):
                if value in mapping and mapping[value] != split:
                    raise ValueError("Speaker or phrasing family leaks across splits")
                mapping[value] = split
            phrase = " ".join(case["reference_text"].casefold().split())
            if phrase and phrase in utterances and utterances[phrase] != split:
                raise ValueError("Reference utterance leaks across splits")
            if phrase:
                utterances[phrase] = split
            cases.append({**case, "split": split})
    return cases


class InterpretOnly:
    """Provide the production interpreter contract with no execution authority."""
    def __init__(self):
        self.interpreter = Interpreter()

    def interpret(self, text, *, original_text=None, on_event=None):
        return self.interpreter.interpret(text, original_text=original_text, on_event=on_event)

    def execute(self, *_args, **_kwargs):
        raise AssertionError("Live evaluation must never execute a command")

    def confirm(self, *_args, **_kwargs):
        raise AssertionError("Live evaluation must never confirm a command")


class ObservedMicrophone(Microphone):
    def __init__(self):
        super().__init__()
        self.audio = None

    def capture(self, on_event=None):
        self.audio = super().capture(on_event=on_event)
        return self.audio


class ObservedASR:
    def __init__(self, delegate):
        self.delegate = delegate
        self.transcript = None

    def transcribe(self, audio):
        self.transcript = self.delegate.transcribe(audio)
        return self.transcript


def _error_label(exc: Exception) -> str:
    if isinstance(exc, LowConfidence): return "low_confidence"
    if isinstance(exc, ClarificationRequired): return "clarification"
    if isinstance(exc, VoiceError):
        message = str(exc)
        if message == "No speech detected": return "no_speech_detected"
        if message == "No command was transcribed": return "empty_transcript"
        if message == "Microphone input overflow": return "microphone_overflow"
        if message.startswith("Microphone unavailable"): return "microphone_unavailable"
        return "voice_error"
    if isinstance(exc, LookupError): return "lookup_error"
    if isinstance(exc, ValueError): return "interpretation_rejected"
    return "unexpected_error"


def evaluate_trial(case: dict, microphone: ObservedMicrophone, asr: ObservedASR,
                   engine: InterpretOnly, *, clock=time.perf_counter) -> dict:
    asr.transcript = None
    microphone.audio = None
    line = Timeline()
    process = psutil.Process()
    before_cpu = process.cpu_times()
    started = clock()
    actual = {"outcome": "abstain"}
    error = None
    try:
        voice = VoiceController(engine, microphone=microphone, asr=asr, clock=clock)
        _, action, line = voice.prepare(line)
        actual = {"outcome": "action", "action": action.kind.value,
                  "target": action.target, "params": dict(action.params)}
    except ClarificationRequired as exc:
        actual = {"outcome": "clarify"}
        error = _error_label(exc)
    except (VoiceError, ValueError, LookupError) as exc:
        error = _error_label(exc)
    except Exception:
        error = "unexpected_error"
    finally:
        audio = microphone.audio
        frames = len(audio) if audio is not None else None
        onset_ms = None
        if audio is not None:
            block = int(microphone.sample_rate * .05)
            for offset in range(0, len(audio), block):
                chunk = audio[offset:offset + block]
                if float(np.sqrt(np.mean(chunk * chunk))) >= microphone.speech_threshold:
                    onset_ms = offset / microphone.sample_rate * 1000
                    break
        microphone.audio = None
    elapsed_ms = (clock() - started) * 1000
    after_cpu = process.cpu_times()
    observed_text = asr.transcript.text if asr.transcript is not None else ""
    asr.transcript = None
    errors, reference_words = word_errors(case["reference_text"], observed_text)
    result = score(case["expected"], actual)
    timings = line.milliseconds()
    final_ms = (round((line.transcription_complete - line.events["speech_end"]) * 1000, 3)
                if line.transcription_complete is not None and "speech_end" in line.events else None)
    return {"id": case["id"], "split": case["split"], "cohort": case["cohort"],
            "kind": case["kind"], "condition": case["condition"],
            "microphone": case["microphone"], "speaking_rate": case["speaking_rate"],
            "tags": case["tags"], "expected_action": case["expected"]["outcome"] == "action",
            "word_errors": errors, "reference_words": reference_words,
            "error_type": error, "audio_frames_in_memory": frames,
            "estimated_speech_onset_ms_from_capture_start": onset_ms,
            "speech_end_to_final_ms": final_ms, "timings_ms": timings,
            "trial_wall_ms": elapsed_ms,
            "trial_cpu_seconds": (after_cpu.user + after_cpu.system
                                  - before_cpu.user - before_cpu.system),
            "rss_mib_after": process.memory_info().rss / 1048576,
            "negative_command_proposal": case["kind"] == "negative" and actual["outcome"] == "action",
            "missed_complete_command": (case["expected"]["outcome"] == "action" and not result["complete"]),
            **result}


def summarize_live(rows: list[dict]) -> dict:
    intended = [row for row in rows if row["kind"] == "intended" and row["expected_action"]]
    matched = [row for row in intended if row["capability"]]
    negative = [row for row in rows if row["kind"] == "negative"]
    wer_rows = [row for row in rows if row["kind"] == "intended" and row["reference_words"] > 0]
    reference_words = sum(row["reference_words"] for row in wer_rows)
    def fraction(n, d): return n / d if d else None
    def quantile(values, pct):
        minimum = 10 if pct == 50 else 20
        return percentile(values, pct) if len(values) >= minimum else None
    final_times = [row["speech_end_to_final_ms"] for row in rows
                   if row["speech_end_to_final_ms"] is not None]
    return {"trials": len(rows), "intended_action_trials": len(intended),
            "negative_triggered_trials": len(negative),
            "wer_intended_trials": fraction(sum(row["word_errors"] for row in wer_rows), reference_words),
            "negative_command_proposal_rate": fraction(sum(row["negative_command_proposal"]
                                                         for row in negative), len(negative)),
            "missed_complete_command_rate": fraction(sum(row["missed_complete_command"]
                                                       for row in intended), len(intended)),
            "complete_command_accuracy": fraction(sum(row["complete"] for row in intended), len(intended)),
            "capability_accuracy": fraction(sum(row["capability"] for row in intended), len(intended)),
            "target_accuracy_given_capability": fraction(sum(row["target"] for row in matched), len(matched)),
            "argument_accuracy_given_capability": fraction(sum(row["arguments"] for row in matched), len(matched)),
            "false_action_proposal_rate_all_trials": fraction(sum(row["false_action"] for row in rows), len(rows)),
            "speech_end_to_final_samples": len(final_times),
            "speech_end_to_final_p50_ms": quantile(final_times, 50),
            "speech_end_to_final_p95_ms": quantile(final_times, 95)}


def summarize_by_split(rows: list[dict]) -> dict:
    result = {}
    for split in sorted({row["split"] for row in rows}):
        selected = [row for row in rows if row["split"] == split]
        result[split] = {"overall": summarize_live(selected),
                         "by_cohort": {cohort: summarize_live([row for row in selected
                                                                if row["cohort"] == cohort])
                                       for cohort in sorted({row["cohort"] for row in selected})}}
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, action="append", required=True)
    parser.add_argument("--consented-live", action="store_true",
                        help="Explicitly opt in to microphone capture after verifying participant consent")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = load_plans(args.plan)
    if not args.consented_live:
        print(json.dumps({"validated_trial_count": len(cases),
                          "splits": {split: sum(case["split"] == split for case in cases)
                                     for split in ("development", "held_out")}}))
        return
    if args.output is None or not args.output.is_absolute() or not _outside_repo(args.output):
        parser.error("Live report output must be an absolute path outside the repository")
    if (not args.output.parent.is_dir() or args.output.parent.is_symlink()
            or not _outside_repo(args.output.parent)):
        parser.error("Live report parent must be an existing private directory outside the repository")
    if args.output.exists():
        parser.error("Live report already exists; overwriting is not supported")
    process = psutil.Process()
    before_cpu = process.cpu_times()
    started = time.perf_counter()
    asr = ObservedASR(LocalASR())
    model_load_ms = (time.perf_counter() - started) * 1000
    rss_after_load = process.memory_info().rss / 1048576
    microphone, engine = ObservedMicrophone(), InterpretOnly()
    rows = []
    print(f"Model ready. {len(cases)} consented trials; no audio or transcript will be saved.")
    interrupted = False
    try:
        for case in cases:
            input(f"Prepare private trial {case['id']} ({case['kind']}); press Enter to capture, Ctrl+C to stop: ")
            rows.append(evaluate_trial(case, microphone, asr, engine))
            print(f"Trial {case['id']} complete. Audio buffer discarded.")
    except KeyboardInterrupt:
        interrupted = True
    after_cpu = process.cpu_times()
    report = {"method": "manually triggered live Microphone -> VoiceController.prepare; no Engine execution",
              "configuration": {**CONFIG, "microphone_sample_rate": microphone.sample_rate,
                                "microphone_max_seconds": microphone.max_seconds,
                                "microphone_silence_seconds": microphone.silence_seconds,
                                "microphone_speech_threshold": microphone.speech_threshold},
              "trial_plan_hashes": [_sha256(path) for path in args.plan],
              "environment": {"platform": platform.platform(), "python": platform.python_version(),
                              "processor": platform.processor(), "logical_cpus": psutil.cpu_count(),
                              "faster_whisper": importlib.metadata.version("faster-whisper"),
                              "source_sha256": {name: _sha256(ROOT / "src" / "aria" / f"{name}.py")
                                                for name in ("voice", "intent", "parser")}},
              "model_load_ms_one_cold_process": model_load_ms,
              "rss_mib_after_load": rss_after_load,
              "wall_seconds_load_and_trials": time.perf_counter() - started,
              "cpu_seconds_load_and_trials": (after_cpu.user + after_cpu.system
                                              - before_cpu.user - before_cpu.system),
              "rss_mib_after_trials": process.memory_info().rss / 1048576,
              "child_processes_after": len(process.children(recursive=True)),
              "interrupted": interrupted,
              "summaries_by_split": summarize_by_split(rows),
              "rows": rows,
              "not_measured": ["real hotkey delivery", "speech-to-verified-result",
                               "OS action execution", "partial transcripts"]}
    with args.output.open("x", encoding="utf-8") as destination:
        json.dump(report, destination, indent=2)
    print(json.dumps({"report_saved": True, "interrupted": interrupted,
                      "trial_counts_by_split": {split: data["overall"]["trials"]
                                                for split, data in report["summaries_by_split"].items()}}))


if __name__ == "__main__":
    main()
