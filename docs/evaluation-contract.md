# Phase 0 command evaluation contract (version 1)

This contract measures the current deterministic command path. It is an evaluation interface, not a new interpreter or an extension of supported behavior. The authoritative product scope and safety boundary remain in [context.md](../context.md).

## Files and freeze rule

- Development cases: tests/data/phase0_development.json. They may guide later rule work.
- Held-out cases: tests/data/phase0_held_out.json. Version 1 SHA-256: **079DB847B852C13AE6AD8C7269ABA71C620D2700561C46E237843B16DF443580**.
- Once the held-out result is reported, do not tune implementation against individual held-out cases or silently edit the file. New evaluation material belongs in a new version with a new hash and a documented reason.
- The old tests/data/intent_eval.json is Sprint 5 development material and is not part of this held-out set.

The corpus is intentionally a **small seed**. Case frequency is not representative of actual user frequency. Phase 0 provides a method and baseline, not Phase 7 acceptance.

## Case schema

Both files are JSON objects with exactly version (integer 1), split (development or held_out), and cases (nonempty array). Each case has:

| Field | Meaning |
| --- | --- |
| id | Unique stable identifier, prefixed dev- or hel- |
| family | Phrasing family; families may not cross splits |
| phenomena | One or more explicit tags such as direct, paraphrase, ambiguous, unsupported, stateful, asr_error, or literal_payload |
| cohort | english, indian_english, or hinglish |
| modality | typed or asr_transcript |
| provenance | authored, simulated_asr, or human_asr |
| context | Explicit tracked_window and foreground_window fixture IDs, each a positive integer or null |
| steps | Nonempty ordered array of text and expected objects |
| voice | Only for human_asr: pseudonymous speaker_id, local consent_record reference, audio_sha256, asr_configuration, and positive audio_duration_ms |

The current ASR-transcript examples are **authored simulations**, not output from human recordings. Human speech acceptance remains future work. For real speech, obtain consent, keep recordings outside Git and local to the evaluation machine, pseudonymize the speaker, retain the ASR configuration and audio hash, and label the observed transcript. The consent record is local; no raw voice or private device data should enter a committed dataset. Version 1 validates this metadata but contains no human_asr cases.

Each expected object is exactly one of:

- **Action:** outcome=action, plus action (existing ActionType), target (semantic fixture identity), and params (typed Action parameters).
- **Clarify:** outcome=clarify. The request needs missing or disambiguating information.
- **Abstain:** outcome=abstain. The request is unsupported or should not be acted upon.

Window targets use window:N after resolution against explicit fixture state. Application targets use app:name. Other literal targets use literal:value. Targetless actions use none. This evaluation compares application/path **proposals**, not real installed-app or filesystem discovery. The controlled window resolver does exercise tracked and foreground references. No catalog of installed applications is introduced.

## Runner and isolation

Run with the existing local Python environment:

    .venv\Scripts\python.exe scripts\phase0_eval.py --iterations 1000

The runner calls Interpreter() with **no model**, validates the proposed Action, and resolves window references against inert fixtures. For multi-step cases it advances state only through fake window/application adapters. It never executes a file, browser, shutdown, volume, screenshot, or other real OS operation. Even correct deletion is recorded as a proposal only. Output goes to ignored logs/phase0-baseline.json. A custom output path may be supplied with --output.

The current interpreter exposes no structured distinction between clarification and abstention. The runner maps a missing tracked/foreground target or an explicit "name the application" error to clarify; other rejections map to abstain. Clarification metrics therefore describe this documented observable heuristic, not a native interpreter response type. The runner does not change parser/interpreter behavior.

## Metrics and denominators

- **Complete outcome accuracy:** exact expected outcome across all steps; actions also require capability, resolved semantic target, and parameters.
- **Complete action accuracy:** fully correct action / steps expecting an action.
- **Capability accuracy:** correct action type / steps expecting an action.
- **Target accuracy given capability:** correct semantic target / steps with correct capability.
- **Parameter accuracy given capability:** exact typed parameters / steps with correct capability. A parameter can be correct even when the target is wrong; complete action still fails.
- **Appropriate abstention:** any non-action response / steps expecting clarify or abstain. This is reported alongside exact clarification accuracy so abstaining on everything cannot appear sufficient.
- **Abstention and clarification rates:** observed respective outcome / all steps.
- **Clarification accuracy:** actual clarify / steps expecting clarify.
- **False action:** any proposed action that is not completely correct, including wrong capability, target, or parameters. Reported per all steps and separately per steps expecting no action.
- **High-risk false proposal:** false action whose actual action is HIGH under the existing RISK registry. Report count and rate per all steps. This is **not** a high-risk execution rate; no real high-risk action is executed.
- **Latency:** elapsed interpretation plus controlled window-reference resolution per case step, with p50/p95. A separate 1,000-iteration warm "open camera" path measures the common deterministic interpretation path.

Undefined conditional metrics are null when their denominator is zero, rather than a misleading zero. Per-case rows retain the expected and observed outcomes for audit. Summaries are split by dataset, cohort, input modality, and phenomenon tags. A case with multiple tags appears in each relevant phenomenon group. Timing and resource samples are machine-specific and not guaranteed performance.

## Reproducibility and integrity

The loader rejects duplicate IDs, duplicate normalized utterances within or across splits, phrasing families crossing splits, malformed annotations, invalid expected Actions, and missing explicit context. It validates human-ASR provenance before such data can enter a future dataset.

The resource measurement records five fresh Python process startup samples, warm interpretation p50/p95, one-second idle CPU sample, RSS, process count, source-tree bytes, and the existing virtual environment's size. There is no distributable installer, so installed package size is explicitly unavailable; source or virtual-environment size must not be described as installer size. The benchmark records OS, Python, processor, and logical CPU count.

This phase does not measure ASR quality on humans, live target-discovery accuracy, execution/verification success, full text-to-action latency, voice end-to-end latency, or release readiness. Those require later controlled and real-world evaluation.
