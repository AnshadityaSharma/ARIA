# Phase 0 deterministic baseline — 2026-10-05

**Status:** measurement foundation established. This is **not** the Phase 7 acceptance gate and does not establish that the current interpreter is good enough.

## Reproduction and environment

Command:

    .venv\Scripts\python.exe scripts\phase0_eval.py --iterations 1000 --output logs\phase0-baseline.json

The JSON report in logs is intentionally ignored by Git. The checked-in contract, corpus, and runner reproduce the scoring method. The held-out version 1 file has SHA-256 **079DB847B852C13AE6AD8C7269ABA71C620D2700561C46E237843B16DF443580**. Do not edit it silently after this report.

Measured on Windows 11 build 26200, Python 3.12.10, Intel Family 6 Model 165 Stepping 2, 16 logical CPUs. The command used the existing local virtual environment and installed no dependency.

## Dataset and method

| Split | Cases | Steps | English | Indian English | Hinglish | Typed cases | Simulated ASR-text cases |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Development | 28 | 31 | 22 | 3 | 3 | 25 | 3 |
| Frozen held-out | 28 | 30 | 22 | 3 | 3 | 25 | 3 |

Each split includes explicit context fixtures, a multi-step follow-up case, direct commands, paraphrases, ambiguous/unsupported requests, and consequential-action proposals. Phrasing families and normalized utterances do not cross splits. Explicit phenomenon tags enable separate breakdowns for direct, paraphrase, natural phrasing, code switching, ambiguity, unsupported requests, compounds, state, simulated ASR errors, and literal payloads. The ASR-text examples are authored simulations; no human speech was captured or measured. See [evaluation-contract.md](evaluation-contract.md) for the schema and denominators.

The runner used Interpreter() with no model. It validated proposed typed actions and resolved window references in a controlled Engine with fake window/application adapters. Only fake window/application operations advanced sequence state. File, browser, shutdown, volume, screenshot, and other real operations were not executed. Thus the figures are interpretation and controlled reference-resolution results, not real execution or verification success.

## Baseline results

| Metric | Development | Held-out |
| --- | ---: | ---: |
| Complete expected outcome, all steps | 19/31 (61.3%) | 18/30 (60.0%) |
| Complete action, expected-action steps | 14/24 (58.3%) | 13/23 (56.5%) |
| Capability, expected-action steps | 15/24 (62.5%) | 14/23 (60.9%) |
| Target, given correct capability | 14/15 (93.3%) | 13/14 (92.9%) |
| Parameters, given correct capability | 15/15 (100%) | 14/14 (100%) |
| Appropriate non-action on expected non-actions | 7/7 (100%) | 7/7 (100%) |
| Exact clarification on expected clarifications | 2/4 (50.0%) | 2/4 (50.0%) |
| False action among all steps | 1/31 (3.2%) | 1/30 (3.3%) |
| False action among expected non-actions | 0/7 | 0/7 |
| High-risk false proposals | 0 | 0 |

The one held-out false action is a simulated ASR-text case: “open note pad” proposed application “note pad” where the annotation expected “notepad.” It was **not** launched on the real computer. Held-out typed cases had 13/20 complete actions; simulated ASR-text cases had 0/3. These very small modality groups are illustrative only.

Each of the Indian English and Hinglish cohorts contains just three held-out cases and currently has 0/3 complete actions. This identifies examples to study later; it is not a population estimate. The held-out set is deliberately small and authored. Its class and cohort proportions do not represent real command frequency. Zero observed high-risk false proposals cannot establish a low field rate.

The current interpreter has no structured clarify/abstain result. The evaluator uses the documented error heuristic in the contract; exact clarification accuracy must be read with that limitation. Application and path targets are scored as proposed normalized names, while window references resolve through fixtures. Installed-application and real-path discovery were not measured here.

Selected held-out phenomenon results (complete expected outcome; tiny, authored groups): direct 9/9, paraphrase 0/3, natural phrasing 0/2, code switching 0/2, ambiguous 1/2, unsupported 3/3, compound 0/1, stateful 4/4, simulated ASR error 0/3. Tags can overlap, so these counts must not be summed.

## Timing and resources

| Measurement | Result |
| --- | ---: |
| Held-out step interpretation plus controlled window resolution, p50 / p95 (30 steps) | 0.0303 / 0.0436 ms |
| Warm “open camera” interpretation, p50 / p95 (1,000 iterations) | 0.0170 / 0.0283 ms |
| Fresh Python process through Interpreter construction, p50 / p95 (5 launches) | 156.36 / 165.92 ms |
| Evaluator process RSS sample | 31.15 MiB |
| Idle process CPU over one second | 0.0% of one logical core in this sample |
| Process count | 1 |
| ARIA source-tree files | 98,184 bytes |
| Existing virtual environment | 383,347,813 bytes |
| Distributable installed size | Unavailable; no installer exists |

The virtual-environment size includes development dependencies and is **not** a packaged installation size. The five fresh-process timings include Python and import startup but do not guarantee cold disk-cache behavior. One-second CPU and RSS samples are not peak or long-run measurements. This Phase 0 benchmark excludes microphone capture, ASR, hotkey/UI, real application launch, native action execution, browser activity, full text-to-action latency, voice end-to-end latency, and real verification.

## Phase 0 conclusion

The contract, split datasets, integrity checks, controlled deterministic runner, and repeatable baseline are in place. These results must not be compared directly with the proposed Phase 7 acceptance thresholds. Before that gate, the corpus needs more representative and consented human speech, broader target fixtures, and a declared release command set. No interpreter behavior was changed to improve this baseline.
