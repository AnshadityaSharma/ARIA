# Phase 1 safety kernel contract

`context.md` is authoritative. This document records the Phase 1 implementation and its limits. Phase 0's frozen command corpus is unchanged; this phase does not change interpretation or run the Phase 7 gate.

## Boundary and contracts

- `ActionType` is the finite capability set. `Action` is the immutable proposal: a capability, an optional target, and scalar typed parameters. `Action.validate()` rejects unsupported fields, absent required targets, invalid ranges, and unknown actions. `RISK` provides fixed metadata for every `ActionType`; `DISPATCH_ACTIONS` must cover the same set.
- The application entry points are `Engine.run_text`, `Engine.execute`, `Engine.confirm`, voice `VoiceController.run_once`, desktop `ActivationController`, and the CLI/UI wrappers. Text and voice submit an `Action` to `Engine.execute`. Only `Engine.confirm` can resume a pending confirmed action. Browser, file, Windows, volume, and shutdown adapters are trusted internal executors and must be invoked through Engine by application code. Python code deliberately calling an adapter directly is outside this process boundary.
- The guarded order is: validate and prepare the typed action; evaluate deterministic risk; create an expiring single-use confirmation for MEDIUM/HIGH (and LOW with `--confirm-low`); bind the prepared action and target; on approval validate and evaluate again; recheck the target; execute through the adapter; check the returned result. `NONE`/default `LOW` actions skip confirmation but still pass validation and risk.
- `Result.ok` means the executor reported completion. `Result.observed` means ARIA read an outcome after execution. `Result.verification` is `UNVERIFIED`, `VERIFIED`, or `FAILED`. `VERIFIED` requires `ok=True` and `observed=True`. `FAILED` and `ok=False` raise `ExecutionFailed` rather than presenting success. A successful but unverified result remains explicit; it is not counted as verified success.

## Confirmation target binding

The confirmation stores the prepared immutable action. File delete/move/rename/copy binds the source's device, identity, size, and modification time; move/rename/copy also bind the intended destination and its absence. Folder creation binds the parent and absence of the new name. Screenshot binds the parent and absent output path. Shutdown binds the fixed local-computer capability. Browser click/submit/download bind the current page object and URL, exact accessible element node, its markup, and current form values; confirmed downloads also bind an existing destination directory or file. Browser confirmation text includes the page URL and role.

Confirmation is rejected if the target cannot be captured or rechecked, if any bound identity changes, if the action is prepared differently, if policy changes, or if the token is invalid, expired, cancelled, superseded, or reused. A confirmed browser action clicks the bound element rather than resolving a different matching node after approval. `--confirm-low` uses the same rule. A confirmed download whose destination does not yet exist fails closed because its destination identity cannot be captured. The default LOW-risk download path remains available without confirmation.

These checks narrow the interval between recheck and execution but do not create an OS-level transactional lock against an external process changing a file or page at the same instant. Browser identity is based on page, node, markup, and form values; arbitrary JavaScript event-handler state cannot be proven immutable. Browser targets with no reliable binding fail closed.

## Current verification status

| Capability/result | Contract status |
| --- | --- |
| Application launch | Observed new matching window; verified |
| Window move/resize | Observed resulting geometry; verified, with constrained geometry reported |
| Folder creation | Observed new directory; verified |
| File move/rename | Observed destination and source disappearance; verified at path level |
| Browser navigation | Observed loaded page URL and non-error HTTP response; verified at navigation level |
| File copy | Destination existence observed; content equivalence unverified |
| Recycle Bin deletion | Source disappearance observed; placement in Recycle Bin unverified |
| Screenshot | Output file existence observed; image content unverified |
| Browser download | Saved file existence observed; downloaded content unverified |
| Other current actions | Executor acknowledgment or adapter-specific data; unverified until a capability-specific check is added |

Verification failure is surfaced as an error. Later capability phases may add stronger checks without changing the kernel contract.

## Timing and reproducibility

Events are `validation_start/complete`, `risk_start/risk_decision`, `target_recheck_start/complete` for confirmations, `execution_start/complete`, and `verification_start/complete`. Existing `action_start/complete` events remain for compatibility. Failure events identify execution or verification failure. `scripts/phase1_kernel_benchmark.py` measures a warm typed `MUTE` action through `Engine` with an inert volume adapter. It reports validation, risk, execution, verification, total kernel p50/p95, one-second idle CPU, RSS, and process count. It excludes interpretation, ASR, real OS action latency, browser startup, and true end-to-end time.

Run controlled tests with the existing environment:

    .venv\Scripts\python.exe -m pytest -q -m "not browser_integration and not desktop_integration and not windows_integration"

    .venv\Scripts\python.exe scripts\phase1_kernel_benchmark.py --iterations 1000 --output logs\phase1-kernel.json

`logs` output is ignored by Git. No real shutdown, delete, browser submit, or download is executed by the Phase 1 contract suite.
