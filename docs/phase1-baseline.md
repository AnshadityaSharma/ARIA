# Phase 1 safety kernel baseline — 2026-10-05

**Status:** Phase 1 controlled acceptance criteria satisfied. This is not Phase 7 interpreter acceptance and does not establish release readiness.

## Method and environment

Command:

    .venv\Scripts\python.exe scripts\phase1_kernel_benchmark.py --iterations 1000 --output logs\phase1-kernel.json

The benchmark ran on Windows 11 build 26200, Python 3.12.10, Intel Family 6 Model 165 Stepping 2, with 16 logical CPUs. It sent a warm typed `MUTE` action through `Engine` using an inert volume adapter. A confirmed `SHUTDOWN` action used an inert shutdown adapter to measure target recheck. It did not invoke the interpreter, microphone, browser, file deletion, or any real operating-system action. Results are machine-specific observations, not guarantees.

## Controlled timing and resources

| Measurement | p50 | p95 |
| --- | ---: | ---: |
| Validation | 0.0086 ms | 0.0302 ms |
| Deterministic risk decision | 0.0066 ms | 0.0245 ms |
| Inert execution | 0.0232 ms | 0.0566 ms |
| Result/verification contract check | 0.0005 ms | 0.0006 ms |
| Confirmed target recheck | 0.0012 ms | 0.0018 ms |
| Full unconfirmed kernel | 0.0483 ms | 0.0954 ms |
| Confirmed kernel after token presentation | 0.0408 ms | 0.0911 ms |

The process used 36.89 MiB RSS at the sample point, used 0.0% of one logical core during a one-second idle sample, and had one process. The measurement excludes confirmation UI time, user response time, real adapter latency, interpreter time, and capability-specific verification work.

## Test evidence

The controlled suite covers complete risk and dispatch registration, invalid actions and ranges, policy bypass attempts, token replay/expiry/cancel/supersession/concurrency, prepared-action immutability, file identity and destination changes, browser page/node/form changes, missing target-binding support, `--confirm-low` file and folder binding, adapter failure, invalid result types, and verification failure. The local browser integration uses a deterministic loopback page and disposable download directory. Real shutdown and real destructive operations are excluded.

## Acceptance and limits

All application entry points inspected route typed actions through `Engine.execute` and confirmed actions through `Engine.confirm`. Every registered action has fixed risk metadata and a dispatch branch. Dispatch follows validation and deterministic policy. Confirmations bind the prepared action and a target snapshot; target changes and targets without reliable binding fail closed. Executor or verification failure cannot be returned as success.

Several existing actions remain explicitly unverified because their adapters do not yet observe the complete effect. These include shutdown acknowledgment, focus/minimize/maximize/restore, open path, volume/mute, browser typing/click/submit, web search/playback beyond their adapter-specific observations, screenshot content, copied-file content, Recycle Bin placement, and downloaded-file content. The exact status is recorded in [phase1-safety-kernel.md](phase1-safety-kernel.md). Later capability phases may strengthen those checks without weakening the kernel.

The Phase 1 acceptance criteria are satisfied for the guarded kernel and controlled adapters. This result does not claim that existing interpreters are accurate enough, that all capabilities are product-stable, or that Phase 7 has passed.
