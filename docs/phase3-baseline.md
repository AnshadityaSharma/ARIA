# Phase 3 stateful deterministic language baseline — 2026-10-07

**Status:** Phase 3 implementation and acceptance checks pass. The predeclared small-corpus diagnostic targets were met. This is not Phase 7 acceptance, real-world accuracy, or evidence of general natural-language understanding.

## Method and integrity

The Phase 3 development corpus contains 20 cases and 22 sequential command steps: 17 English, 3 Hinglish, and 2 Indian-English steps; 20 typed and 2 simulated-ASR transcript steps. Six steps require non-action behavior. Every case declares starting tracked/foreground state. Case IDs, phrasing families, and normalized utterances are checked against both Phase 0 splits.

The frozen Phase 0 held-out file remained byte-identical with SHA-256 `079DB847B852C13AE6AD8C7269ABA71C620D2700561C46E237843B16DF443580`. Rules and the new development corpus were frozen before the held-out evaluator was run once. Evaluation used inert adapters and controlled discovered application records; no OS, browser, file, or destructive adapter was reached. Exact JSON is in [phase3-evaluation.json](phase3-evaluation.json).

## Evaluation results

| Metric | Phase 0 historical held-out | Phase 3, original Phase 0 method | Phase 3, resolution-aware held-out |
| --- | ---: | ---: | ---: |
| Capability accuracy | 14/23 (60.9%) | 23/23 (100%) | 23/23 (100%) |
| Complete-action accuracy | 13/23 (56.5%) | 22/23 (95.7%) | 23/23 (100%) |
| Target accuracy given correct capability | 92.9% | 22/23 (95.7%) | 23/23 (100%) |
| Parameter accuracy given correct capability | 100% | 23/23 (100%) | 23/23 (100%) |
| Appropriate non-action | 7/7 (100%) | 7/7 (100%) | 7/7 (100%) |
| Clarification accuracy | 2/4 (50%) | 4/4 (100%) | 4/4 (100%) |
| False actions on non-actions | 0/7 | 0/7 | 0/7 |
| High-risk false proposals | 0/30 | 0/30 | 0/30 |

The original method's remaining complete-action miss is a raw application spelling target; its parser target is resolved to the exact discovered application by the Phase 2 resolver. Resolution-aware scoring observes that boundary. The predeclared diagnostic targets of at least 21/23 capability and 20/23 complete action were met under both current views. These targets apply only to this small authored corpus.

The Phase 3 development set scored 16/16 complete actions, 6/6 appropriate non-actions, 3/3 required clarifications, zero false actions, and zero high-risk false proposals. Its four stateful steps passed, including missing-context clarification and a launch → resize → placement chain. Hinglish scored 3/3 and Indian English 2/2. Cohort sizes are too small for generalization claims.

## Timing and resources

Measurements ran on Windows 11 build 26200, Python 3.12.10, Intel Family 6 Model 165 Stepping 2, 16 logical CPUs, and 31.75 GiB RAM. Warm operations used 2,000 samples; startup used 10 fresh processes; p50/p95 use linear interpolation over wall-clock milliseconds. Exact data is in [phase3-measurements.json](phase3-measurements.json).

| Measurement | p50 | p95 |
| --- | ---: | ---: |
| Normalization | 0.013 ms | 0.029 ms |
| Direct grammar | 0.044 ms | 0.140 ms |
| Paraphrase grammar | 0.051 ms | 0.090 ms |
| Hinglish grammar | 0.041 ms | 0.085 ms |
| Parameter command parsing | 0.063 ms | 0.125 ms |
| State reference resolution | 0.0003 ms | 0.0004 ms |
| Exact dynamic application resolution | 0.0015 ms | 0.0016 ms |
| Compact dynamic application resolution | 0.0066 ms | 0.0091 ms |
| One-edit dynamic application resolution | 0.0146 ms | 0.0189 ms |
| Full direct interpretation | 0.048 ms | 0.082 ms |
| Full paraphrase interpretation | 0.051 ms | 0.086 ms |
| Full Hinglish interpretation | 0.042 ms | 0.067 ms |
| Clarification | 0.016 ms | 0.033 ms |
| Abstention | 0.014 ms | 0.021 ms |
| Fresh process startup plus interpretation | 167.78 ms | 195.50 ms |

The direct warm path met the proposed 0.05 ms p50 / 0.10 ms p95 objective. Paraphrase p50 was 0.051 ms, effectively at the objective but 0.001 ms above it; its p95 met the objective. The objective is diagnostic and machine-specific, not a guarantee. The first in-process interpretation was 2.38 ms.

At the sample point the process used 31.30 MiB RSS, 0.0% of one logical CPU during a one-second idle interval, and one process. The ARIA Python source tree was 136,104 bytes, 37,920 bytes above the Phase 0 recorded tree; that cumulative change includes accepted Phases 1–3. `pyproject.toml` and `uv.lock` were unchanged in Phase 3, so dependency-manifest size changed by 0 bytes and no dependency was added.

## Acceptance and limitations

Phase 3 acceptance is satisfied: unclear, negated, compound, unsupported, expired, missing, ambiguous, and stale-reference requests cannot silently become another action; verified state rules and dynamic application resolution pass; failures have explicit categories; the Phase 1 guarded path remains the only execution path.

The remaining categories are evidence gaps rather than observed corpus failures: broader natural paraphrases, larger Hinglish/Indian-English samples, real ASR and human voice, user-frequency estimates, and application errors outside the deliberately narrow discovery-derived matcher. Those belong to later measurement gates. Phase 7 was not run, and Phase 3 does not authorize a learned interpreter.
