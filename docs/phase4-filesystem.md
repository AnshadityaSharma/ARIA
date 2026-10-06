# Phase 4 guarded filesystem contract

`context.md` is authoritative. This document records the Phase 4 boundary. Filesystem commands are deterministic, local, and capability based. They do not use a classifier, embeddings, a generative model, Qwen, or llama.cpp, and they do not create a background process.

## Execution boundary

Every filesystem command follows the existing guarded path:

    deterministic interpretation → typed Action → validation → deterministic risk
    → confirmation when required → target recheck → execution → verification

`Engine` is the only execution entry point. `CREATE_FOLDER`, `OPEN_PATH`, and `COPY_PATH` retain their declared none/low risk policy. `MOVE_PATH` and `RENAME_PATH` are medium risk, and `DELETE_PATH` is high risk. Move, rename, and delete always require confirmation. When `confirm_low` is enabled, create and copy use the same binding and recheck contract before execution.

The confirmation binds the validated action, canonical absolute paths, source identity, source metadata or content evidence required by the operation, and destination-parent identity. It displays the exact source, destination where applicable, object type, and consequence. A changed, missing, ambiguous, inaccessible, or unidentifiable target invalidates confirmation.

## Resolution and identity

`PathResolver` captures its base directory when constructed. Absolute paths remain absolute; relative paths resolve against that captured base. Explicit known-folder scopes resolve through the Windows Known Folder API. A bare filename may match an exact direct child of the base or a known folder only when the result is unique. Ambiguity requires clarification. Resolution never performs fuzzy matching or an unbounded recursive machine search.

UNC and device paths, drive-relative paths, alternate data streams, wildcards, reserved Windows device names, and reparse-point traversal are rejected. Existing destinations are rejected; overwrite is not an action parameter or hidden fallback. Destination parents must already exist and are identity bound before mutation.

`PathSnapshot` records the canonical path, object kind, volume/device identity, stable file identity, mode, size and timestamps, parent identity, reparse status, and optional metadata manifest or streaming SHA-256 content evidence. On Windows, Python's standard-library `st_dev` and `st_ino` values provide the volume and file identity. Missing or zero identity fails closed.

## Operation and verification contracts

| Capability | Execution | Verification | State effect |
| --- | --- | --- | --- |
| Create folder | Exclusive create | Destination is a new directory under the rebound parent | Update verified `FileState` |
| Open path | Windows shell open | Request acceptance only; resulting UI is not correlated | `UNVERIFIED`; no state update |
| Copy | Exclusive copy | Destination type/size and streaming content digest match source | Update verified `FileState` |
| Same-volume move | Atomic no-replace rename | Stable object identity at destination and source absence | Update verified `FileState` |
| Cross-volume move | Copy, verify, then remove source | Destination content matches the pre-execution source and source is absent | Update verified `FileState` |
| Rename | Atomic no-replace rename | Stable object identity at destination and source absence | Update verified `FileState` |
| Recycle Bin delete | Windows Recycle Bin request | Source absence is observed; the resulting Recycle Bin item is not correlated | `UNVERIFIED`; clear matching state |

On failed verification, ARIA returns `FAILED`, records rollback/recovery information, and does not update `FileState`. Newly created copy/folder output is removed only when its exact identity still matches. Move/rename rollback is attempted only for the exact verified moved object and only while the original location remains free. Permission and access failures propagate as failures and do not update state.

Content hashing is operation specific. Ordinary metadata resolution does not hash content. Copy and cross-volume move use streaming SHA-256 because content equivalence is the required result. Directory metadata manifests bind shape and identities; directory content verification additionally hashes file content. Measurements report bytes and entries because no single latency applies to every file tree.

## Recent file state and language

`FileState` contains only the most recent successfully verified path operation, including path, stable identity, kind, capability, and update time. It expires after five minutes and is rechecked before use. `open that file/folder` and copy references may use compatible verified state. Move, rename, and delete require an explicit path and never consume implicit recent-file state.

The finite grammar preserves quoted and unquoted literal filename/path payloads. Control-text negation and multi-action guards run outside quoted literals. Missing separators, vague destructive targets, compound commands, and incompatible references require clarification or abstention. Application discovery remains separate; there is no filesystem target catalogue.

## Reproduction

Controlled contracts and benchmark contract:

    .venv\Scripts\python.exe -m pytest -q tests\test_phase4_filesystem.py tests\test_phase4_benchmark.py

Safe native Windows tests, using only generated temporary fixtures:

    set ARIA_FILESYSTEM_INTEGRATION=1
    .venv\Scripts\python.exe -m pytest -q tests\test_filesystem_integration.py

Measurements:

    .venv\Scripts\python.exe scripts\phase4_filesystem_benchmark.py --iterations 30 --large-iterations 10 --output docs\phase4-measurements.json

