# Phase 2 Windows baseline — 2026-10-06

**Status:** Phase 2 implementation and available controlled/native acceptance checks pass. This is not Phase 7 interpreter acceptance or release readiness. Live second-monitor evidence and verified path-handler UI correlation remain limitations.

## Method and environment

The benchmark used a native disposable Tk window, a generated UUID-named Start Menu shortcut and disposable fixture application, and an inert path opener. It ran on Windows 11 build 26200, Python 3.12.10, Intel Family 6 Model 165 Stepping 2, 16 logical CPUs, and 31.75 GiB RAM. The machine had one 1536×960 monitor with virtual origin `(0, 0)`.

Warm operation samples use wall-clock milliseconds. p50/p95 use linear interpolation over sorted samples. Discovery cold has one sample; its “p95” is therefore only that observation. Application launch has three samples. Other measurements have ten samples. Exact JSON is in [phase2-measurements.json](phase2-measurements.json).

## Timing and resources

| Measurement | Samples | p50 | p95 |
| --- | ---: | ---: | ---: |
| Application discovery, cold | 1 | 2515.32 ms | 2515.32 ms |
| Application discovery, warm cached | 10 | 0.0013 ms | 0.0044 ms |
| Window enumeration | 10 | 1.98 ms | 2.31 ms |
| Named target resolution | 10 | 2.12 ms | 2.21 ms |
| Stable identity recheck | 10 | 0.117 ms | 0.139 ms |
| Known-folder resolution | 10 | 0.012 ms | 2.14 ms |
| Focus to verified foreground | 10 | 4.93 ms | 17.60 ms |
| Move to verified geometry | 10 | 2.10 ms | 3.24 ms |
| Resize to verified/constrained geometry | 10 | 3.69 ms | 6.42 ms |
| Minimize to verified placement | 10 | 0.93 ms | 7.41 ms |
| Maximize to verified placement | 10 | 0.55 ms | 2.54 ms |
| Restore to verified placement | 10 | 0.58 ms | 0.73 ms |
| Full deterministic text to verified native result | 10 | 5.91 ms | 13.02 ms |
| Path request to explicit unverified result, inert opener | 10 | 2.24 ms | 2.56 ms |
| Fresh Engine process startup | 10 | 358.91 ms | 534.34 ms |
| Dynamic application launch to verified window | 3 | 3570.78 ms | 3998.59 ms |

At the final sample point the benchmark process used 60.13 MiB RSS, 0.0% of one logical core during a one-second idle interval, and one process. No GPU or learned model participated. The proposed native move/focus target is p95 below 500 ms; both observations met it on this machine. This is a proposed target under validation, not a product guarantee.

Cold Start Apps discovery and its mandatory pre-launch refresh dominate application launch. The two-second discovery cache makes repeated reads inexpensive while preserving automatic refresh for newly installed applications. These timings are specific to this Windows build and hardware.

## Test evidence

The default suite passed **194 tests** with **11 opt-in tests skipped**. It includes the Phase 0 evaluator/integrity contracts and Phase 1 safety-kernel contracts. The focused native Phase 2 run passed **3 tests**: verified disposable-window focus/placement/move/resize, vanished-target rejection, and UUID-named dynamic Start Menu discovery plus verified launch. The live second-monitor check skipped because only one monitor was connected. Controlled negative-coordinate monitor geometry passed.

Phase 2 tests cover duplicate Start Apps records, exact/unique-substring application resolution, missing/ambiguous applications, exact AppID launch, changed registration rejection, exact-title/executable/application window resolution, ambiguity, unreliable identity, reused HWND rejection, verified focus/placement/geometry, constrained results, relative resize, top-right placement, restore-before-geometry, failed-verification state preservation, known folders, and explicit unverified path results.

## Limits and acceptance

- `OPEN_PATH` verifies the filesystem target and dispatch but cannot correlate all possible Windows handler UIs, so it remains explicitly `UNVERIFIED`.
- A physical second-monitor execution was unavailable. Negative coordinates and monitor-relative calculations have controlled coverage, but live multi-monitor evidence remains outstanding.
- Start Apps cold refresh is slow on this machine, and three launch samples are too few for a broad latency claim.
- Window application identity is best effort because some classic Win32 processes expose no AppUserModelID. HWND/PID/process-creation identity still guards mutation.
- Foreground activation remains subject to Windows policy; ARIA uses thread-input attachment and verifies the resulting exact foreground target, failing closed if Windows refuses it.

The implementation criteria are satisfied for dynamic discovery, guarded stable-window control, ambiguity/stale-target rejection, verification, and generated-application acceptance. The explicitly permitted second-monitor skip and `OPEN_PATH` unverified contract are documented evidence gaps rather than claimed successes. No Phase 3 work or Phase 7 gate was performed.
