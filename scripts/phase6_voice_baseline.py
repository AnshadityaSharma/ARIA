"""Local, execution-free replay of consented voice clips through the unchanged ASR/parser.

No microphone is opened. Reports contain aggregate metrics and case IDs, never audio,
reference text, or observed transcripts. Human manifests and audio must stay outside Git.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import time
from pathlib import Path

import psutil

from aria.core import Action, ActionType
from aria.intent import Interpreter
from aria.parser import ClarificationRequired
from aria.voice import LocalASR, VoiceError, normalize

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"model": "base", "device": "cpu", "compute_type": "int8",
          "local_files_only": True, "beam_size": 1, "best_of": 1,
          "vad_filter": True, "min_silence_duration_ms": 300,
          "condition_on_previous_text": False, "min_confidence": .35}
COHORTS = {"english", "indian_english", "hinglish"}
OUTCOMES = {"action", "clarify", "abstain"}
FIELDS = {"id", "family", "speaker_id", "cohort", "condition", "microphone",
          "speaking_rate", "tags", "audio_path", "audio_sha256", "reference_text",
          "expected", "consent_record"}


def _outside_repo(path: Path) -> bool:
    return not path.resolve().is_relative_to(ROOT.resolve())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifests(paths: list[Path]) -> list[dict]:
    cases, ids, split_speakers, split_families, utterances = [], set(), {}, {}, {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if set(data) != {"version", "source", "split", "cases"} or data["version"] != 1:
            raise ValueError("Invalid voice manifest header")
        source, split = data["source"], data["split"]
        if source not in {"human", "synthetic"} or split not in {"development", "held_out", "smoke"}:
            raise ValueError("Invalid voice source or split")
        if source == "human" and (split == "smoke" or not _outside_repo(path)):
            raise ValueError("Human manifest must be a development/held-out file outside the repository")
        if source == "synthetic" and split != "smoke":
            raise ValueError("Synthetic audio is smoke-only")
        if not isinstance(data["cases"], list) or not data["cases"]:
            raise ValueError("Voice manifest has no cases")
        for case in data["cases"]:
            if not isinstance(case, dict) or set(case) != FIELDS:
                raise ValueError("Invalid voice case fields")
            if not all(isinstance(case[k], str) and case[k].strip() for k in
                       ("id", "family", "speaker_id", "cohort", "condition",
                        "microphone", "speaking_rate", "audio_path", "audio_sha256")):
                raise ValueError("Missing voice annotation")
            if not isinstance(case["reference_text"], str):
                raise ValueError("Reference text must be a string")
            if case["id"] in ids or case["cohort"] not in COHORTS:
                raise ValueError("Duplicate ID or invalid cohort")
            ids.add(case["id"])
            if not isinstance(case["tags"], list) or not case["tags"] or not all(
                    isinstance(tag, str) and tag for tag in case["tags"]):
                raise ValueError("Voice case needs tags")
            expected = case["expected"]
            if not isinstance(expected, dict) or expected.get("outcome") not in OUTCOMES:
                raise ValueError("Invalid expected outcome")
            if expected["outcome"] == "action" and not words(case["reference_text"]):
                raise ValueError("Expected action needs audible reference words")
            if expected["outcome"] == "action":
                if set(expected) != {"outcome", "action", "target", "params"}:
                    raise ValueError("Action expectation needs action, target, and params")
                if not isinstance(expected["target"], (str, type(None))) or not isinstance(expected["params"], dict):
                    raise ValueError("Invalid action target or parameters")
                Action(ActionType(expected["action"]), expected["target"], expected["params"]).validate()
            elif set(expected) != {"outcome"}:
                raise ValueError("Non-action expectation has extra fields")
            audio = Path(case["audio_path"])
            if not audio.is_absolute():
                audio = (path.parent / audio).resolve()
            if source == "human":
                consent = case["consent_record"]
                if (not isinstance(consent, str) or not Path(consent).is_absolute()
                        or not _outside_repo(audio) or not _outside_repo(Path(consent))
                        or not Path(consent).is_file()):
                    raise ValueError("Human audio and consent record must exist outside the repository")
                if not re.fullmatch(r"[a-fA-F0-9]{64}", case["audio_sha256"]):
                    raise ValueError("Human audio needs a SHA-256 hash")
            elif case["consent_record"] is not None:
                raise ValueError("Synthetic case has no human consent record")
            if not audio.is_file() or _sha256(audio).casefold() != case["audio_sha256"].casefold():
                raise ValueError(f"Audio missing or hash mismatch for {case['id']}")
            for mapping, value in ((split_speakers, case["speaker_id"]),
                                   (split_families, case["family"])):
                if value in mapping and mapping[value] != split:
                    raise ValueError("Speaker or phrasing family leaks across splits")
                mapping[value] = split
            phrase = " ".join(case["reference_text"].casefold().split())
            if phrase and phrase in utterances and utterances[phrase] != split:
                raise ValueError("Reference utterance leaks across splits")
            if phrase:
                utterances[phrase] = split
            cases.append({**case, "source": source, "split": split, "audio": audio})
    return cases


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def word_errors(reference: str, observed: str) -> tuple[int, int]:
    left, right = words(reference), words(observed)
    previous = list(range(len(right) + 1))
    for i, token in enumerate(left, 1):
        current = [i]
        for j, candidate in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j-1] + (token != candidate)))
        previous = current
    return previous[-1], len(left)


def proposal(text: str, interpreter: Interpreter, confidence: float = 1.0) -> dict:
    if confidence < CONFIG["min_confidence"]:
        return {"outcome": "abstain", "reason": "confidence"}
    try:
        action = interpreter.interpret(normalize(text), original_text=text).validate()
        return {"outcome": "action", "action": action.kind.value,
                "target": action.target, "params": dict(action.params)}
    except ClarificationRequired:
        return {"outcome": "clarify"}
    except (ValueError, LookupError):
        return {"outcome": "abstain"}


def score(expected: dict, actual: dict) -> dict:
    wanted = expected["outcome"] == "action"
    capability = wanted and actual["outcome"] == "action" and expected["action"] == actual["action"]
    target = capability and (expected["target"].casefold() == actual["target"].casefold()
                             if isinstance(expected["target"], str) and isinstance(actual["target"], str)
                             else expected["target"] == actual["target"])
    arguments = capability and expected["params"] == actual["params"]
    complete = (capability and target and arguments) if wanted else expected["outcome"] == actual["outcome"]
    return {"complete": complete, "capability": capability, "target": target,
            "arguments": arguments, "false_action": actual["outcome"] == "action" and not complete}


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize(rows: list[dict]) -> dict:
    action = [row for row in rows if row["expected_action"]]
    matched = [row for row in action if row["capability"]]
    nonaction = [row for row in rows if not row["expected_action"]]
    wer_rows = [row for row in rows if row["reference_words"] > 0]
    def ratio(numerator, denominator): return numerator / denominator if denominator else None
    reference_words = sum(row["reference_words"] for row in wer_rows)
    warm_asr = [row["asr_ms"] for row in rows[1:]]
    def p50(values): return percentile(values, 50) if len(values) >= 10 else None
    def p95(values): return percentile(values, 95) if len(values) >= 20 else None
    return {
        "clips": len(rows), "expected_action_clips": len(action), "expected_nonaction_clips": len(nonaction),
        "wer": ratio(sum(row["word_errors"] for row in wer_rows), reference_words),
        "reference_words": reference_words,
        "complete_outcome_accuracy": ratio(sum(row["complete"] for row in rows), len(rows)),
        "capability_accuracy": ratio(sum(row["capability"] for row in action), len(action)),
        "target_accuracy_given_capability": ratio(sum(row["target"] for row in matched), len(matched)),
        "argument_accuracy_given_capability": ratio(sum(row["arguments"] for row in matched), len(matched)),
        "false_action_rate_all_clips": ratio(sum(row["false_action"] for row in rows), len(rows)),
        "false_action_rate_nonaction_clips": ratio(sum(row["false_action"] for row in nonaction), len(nonaction)),
        "missed_action_rate_file_replay": ratio(sum(row["missed_action"] for row in action), len(action)),
        "first_clip_asr_ms": rows[0]["asr_ms"] if rows else None,
        "warm_asr_samples": len(warm_asr),
        "warm_asr_p50_ms": p50(warm_asr), "warm_asr_p95_ms": p95(warm_asr),
        "asr_p50_ms": p50([row["asr_ms"] for row in rows]),
        "asr_p95_ms": p95([row["asr_ms"] for row in rows]),
        "decode_p50_ms": p50([row["decode_ms"] for row in rows]),
        "parse_p50_ms": p50([row["parse_ms"] for row in rows]),
    }


def summarize_by_split(rows: list[dict]) -> dict:
    return {source: {split: summarize([row for row in rows
                                      if row["source"] == source and row["split"] == split])
                     for split in sorted({row["split"] for row in rows if row["source"] == source})}
            for source in sorted({row["source"] for row in rows})}


def summarize_by_cohort(rows: list[dict]) -> dict:
    return {source: {split: {cohort: summarize([row for row in rows
                                               if row["source"] == source and row["split"] == split
                                               and row["cohort"] == cohort])
                            for cohort in sorted({row["cohort"] for row in rows
                                                  if row["source"] == source and row["split"] == split})}
                     for split in sorted({row["split"] for row in rows if row["source"] == source})}
            for source in sorted({row["source"] for row in rows})}


def run(paths: list[Path]) -> dict:
    from faster_whisper import decode_audio
    cases = load_manifests(paths)
    process = psutil.Process()
    interpreter = Interpreter()
    cpu_before = process.cpu_times()
    started = time.perf_counter()
    asr = LocalASR()
    model_load_ms = (time.perf_counter() - started) * 1000
    rss_after_load = process.memory_info().rss / 1048576
    rows = []
    for case in cases:
        before = time.perf_counter()
        audio = decode_audio(str(case["audio"]))
        decode_ms = (time.perf_counter() - before) * 1000
        before = time.perf_counter()
        try:
            transcript = asr.transcribe(audio)
            observed_text, confidence = transcript.text, transcript.confidence
            asr_error = None
        except VoiceError as exc:
            if str(exc) != "No command was transcribed":
                raise
            observed_text, confidence = "", 0.0
            asr_error = "empty_transcript"
        asr_ms = (time.perf_counter() - before) * 1000
        before = time.perf_counter()
        actual = proposal(observed_text, interpreter, confidence)
        parse_ms = (time.perf_counter() - before) * 1000
        reference = proposal(case["reference_text"], interpreter)
        errors, count = word_errors(case["reference_text"], observed_text)
        result = score(case["expected"], actual)
        reference_result = score(case["expected"], reference)
        rows.append({"id": case["id"], "source": case["source"], "split": case["split"],
                     "cohort": case["cohort"], "condition": case["condition"],
                     "microphone": case["microphone"], "speaking_rate": case["speaking_rate"],
                     "tags": case["tags"], "expected_action": case["expected"]["outcome"] == "action",
                     "missed_action": (case["expected"]["outcome"] == "action"
                                       and actual["outcome"] != "action"),
                     "word_errors": errors, "reference_words": count, "decode_ms": decode_ms,
                     "asr_ms": asr_ms, "parse_ms": parse_ms,
                     "asr_error": asr_error,
                     "confidence_rejected": actual.get("reason") == "confidence",
                     "reference_proposal_correct": reference_result["complete"],
                     "error_boundary": ("none" if result["complete"] else
                         "reference_interpretation" if not reference_result["complete"] else
                         "confidence_gate" if actual.get("reason") == "confidence" else
                         "asr_or_recorded_audio" if errors else "interpretation_context"),
                     **result})
    cpu_after = process.cpu_times()
    wall_seconds = time.perf_counter() - started
    summaries = summarize_by_split(rows)
    return {"method": "Offline file decode -> unchanged LocalASR -> unchanged deterministic Interpreter; no OS actions",
            "configuration": CONFIG, "environment": {"platform": platform.platform(),
            "python": platform.python_version(), "processor": platform.processor(),
            "logical_cpus": psutil.cpu_count(),
            "packages": {name: importlib.metadata.version(name)
                         for name in ("faster-whisper", "ctranslate2", "numpy")},
            "source_sha256": {name: _sha256(ROOT / "src" / "aria" / f"{name}.py")
                              for name in ("voice", "intent", "parser")}},
            "manifests": [{"sha256": _sha256(path), "source": json.loads(path.read_text(encoding="utf-8"))["source"]}
                          for path in paths],
            "model_load_ms_one_cold_process": model_load_ms,
            "resources": {"rss_mib_after_load": rss_after_load,
                          "rss_mib_after_cases": process.memory_info().rss / 1048576,
                          "wall_seconds_load_and_cases": wall_seconds,
                          "cpu_seconds_load_and_cases": (cpu_after.user + cpu_after.system
                                                         - cpu_before.user - cpu_before.system),
                          "child_processes_after": len(process.children(recursive=True))},
            "summaries": summaries, "cohort_summaries": summarize_by_cohort(rows), "rows": rows,
            "not_measured": ["live microphone capture and endpointing", "false activations",
                             "missed live commands", "partial transcript latency",
                             "speech-end-to-verified-result", "execution/verification",
                             "long-idle resource use"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.manifest)
    encoded = json.dumps(report, indent=2)
    contains_human = "human" in report["summaries"]
    if contains_human and (args.output is None or not args.output.is_absolute()
                           or not _outside_repo(args.output)
                           or not args.output.parent.is_dir()
                           or args.output.parent.is_symlink()
                           or not _outside_repo(args.output.parent)):
        parser.error("Human report needs an existing private output directory outside the repository")
    if args.output and args.output.exists():
        parser.error("Report already exists; overwriting is not supported")
    if args.output:
        if not contains_human:
            args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            destination.write(encoded)
    if contains_human:
        print(json.dumps({"report_saved": True,
                          "splits": {split: summary["clips"] for split, summary
                                     in report["summaries"]["human"].items()}}))
    else:
        print(encoded)


if __name__ == "__main__":
    main()
