# Phase 3 deterministic language contract

`context.md` is authoritative. This document records the Phase 3 boundary. The interpreter is a bounded deterministic command language, not a general chatbot. It does not use a classifier, embeddings, a generative model, Qwen, or llama.cpp.

## Interpretation contract

Input is normalized with Unicode NFKC, bounded whitespace and terminal-punctuation cleanup, case-folded control tokens, and source spans. Matching returns exactly one validated typed `Action`, raises `ClarificationRequired` when the user must disambiguate, raises `UnsupportedCommand` when no supported action should be proposed, or rejects malformed input. Successful actions continue through the Phase 1 Engine boundary:

    interpretation → typed action → validation → deterministic risk → confirmation
    → target recheck → execution → verification

Negated commands produce no action. Requests containing multiple actionable clauses require clarification and are never partially interpreted. The guard recognizes command conjunctions only in control text; search queries, URLs, paths, application names, filenames, and typed text remain literal payloads. Empty, oversized, control-character, and model-delimiter input is rejected.

The finite grammar covers measured English variants, bounded Indian-English polite forms, and a small explicit Hinglish vocabulary. It extracts supported word/digit percentages, relative size changes, directions, and movement amounts. These rules are deliberately finite. A new phrase is added only from development evidence and must remain compatible with conservative abstention.

## References and state

`it`, `that`, and `that window` refer to the most recent compatible verified window. `this window`, `the window`, and `current`/`active window` refer to the stable foreground identity captured at command start. Recent state expires after five minutes. Missing, expired, unverified, incompatible, vanished, or identity-changed references require clarification. Engine performs the Phase 2 stable HWND/PID/process-creation recheck before any mutation.

Tracked state changes only after successful verification. An executor success with `UNVERIFIED` or failed verification cannot establish or refresh a recent target. A legacy adapter without stable identity cannot establish verified recent state.

## Dynamic application names

Application names come only from current Windows discovery. Resolution tries normalized exact name, whitespace-insensitive exact name, existing unique substring, then optional unique edit-distance-one recovery when the query is one alphanumeric token of at least five characters. Every ambiguous tier fails closed. The recovery rule is never applied to paths, URLs, searches, typed text, or consequential file targets. No application catalogue is embedded in the grammar.

## Reproduction

Development and integrity tests:

    .venv\Scripts\python.exe -m pytest -q tests\test_phase3_language.py tests\test_phase3_eval.py

Controlled measurements:

    .venv\Scripts\python.exe -m scripts.phase3_benchmark --iterations 2000 --startup-iterations 10 --output docs\phase3-measurements.json

The one Phase 3 diagnostic evaluation, already recorded after development freeze, is in `docs/phase3-evaluation.json`. It verifies the frozen Phase 0 held-out hash before reading results. It is not a Phase 7 acceptance run and must not be rerun for rule tuning.
