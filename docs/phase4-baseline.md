# Phase 4 filesystem baseline — 2026-10-07

**Status:** Phase 4 implementation and acceptance checks pass within the declared local-filesystem scope. This is not Phase 7 acceptance and does not claim autonomous organization, content understanding, or general filesystem intelligence.

## Method and integrity

All controlled tests used disposable temporary trees. Native Windows integration used generated temporary files and folders; the Recycle Bin test sent only its own uniquely named disposable file and did not inspect or modify existing Recycle Bin contents. No user document was used. The frozen Phase 0 held-out file remained byte-identical with SHA-256 `079DB847B852C13AE6AD8C7269ABA71C620D2700561C46E237843B16DF443580`.

The complete suite passed **262 tests** and skipped **16** opt-in or unavailable-environment tests. The Phase 4 contract subset passed **28 tests** and skipped one native symlink-creation case. With native filesystem integration enabled, **3 tests passed** and the native cross-volume case skipped because no disposable second-volume root was configured. Controlled cross-volume behavior, reparse rejection, negative cases, target changes, destination-parent changes, collisions, collision races, access errors, confirmation cancellation/expiry, externally changed rollback targets, verification failures, rollback data, and FileState rules passed.

## Capability and safety results

Create, copy, same-volume move, cross-volume move, and rename produce on-disk `VERIFIED` results under the contract in [phase4-filesystem.md](phase4-filesystem.md). Open-path remains explicitly `UNVERIFIED` because shell request acceptance does not identify the opened UI. Recycle Bin deletion observes source absence but remains `UNVERIFIED` because ARIA does not correlate the resulting Recycle Bin entry.

Move, rename, and delete always require confirmation. Confirmations are bound to the exact source identity and destination-parent identity, and the final target is rechecked after the user responds. Low-risk create/copy uses the same final recheck when `confirm_low` is configured. A changed source, changed destination parent, newly occupied destination, missing identity, reparse point, collision, or ambiguous resolution fails closed. Failed or unverified operations do not establish recent verified file state. Verified state expires after five minutes, and destructive actions reject implicit recent-file references.

## Timing and resource results

Measurements ran on Windows 11 build 26200, Python 3.12.10, Intel Family 6 Model 165 Stepping 2, 16 logical CPUs, and 31.75 GiB RAM. Standard samples use 30 runs, 8 MiB hashing uses 10, and startup uses 10 fresh processes. p50/p95 use linear interpolation over wall-clock milliseconds. Exact values are in [phase4-measurements.json](phase4-measurements.json).

| Measurement | p50 | p95 |
| --- | ---: | ---: |
| Absolute path resolution | 0.120 ms | 0.165 ms |
| Bare exact-name resolution | 0.438 ms | 0.571 ms |
| Known-folder resolution | 0.076 ms | 0.084 ms |
| File metadata snapshot | 0.123 ms | 0.134 ms |
| Metadata manifest, 25 entries | 0.443 ms | 0.757 ms |
| Confirmation binding | 0.351 ms | 0.622 ms |
| Identity recheck | 0.285 ms | 0.609 ms |
| Confirmation display construction | 0.0013 ms | 0.0035 ms |
| Create and verify | 2.446 ms | 3.028 ms |
| Copy 1 MiB and verify | 15.009 ms | 17.046 ms |
| Same-volume move and verify | 11.737 ms | 14.352 ms |
| Rename and verify | 9.077 ms | 9.921 ms |
| Full text to verified copy | 10.863 ms | 11.848 ms |
| Full text to pending confirmation | 5.038 ms | 6.466 ms |
| Fresh process startup | 223.565 ms | 308.939 ms |

### Hashing and manifest scaling

| Fixture | Bytes | Entries | Verification | p50 | p95 |
| --- | ---: | ---: | --- | ---: | ---: |
| Small file | 4,096 | 1 | Streaming SHA-256 | 0.798 ms | 1.302 ms |
| Medium file | 1,048,576 | 1 | Streaming SHA-256 | 2.869 ms | 4.142 ms |
| Larger file | 8,388,608 | 1 | Streaming SHA-256 | 20.220 ms | 20.919 ms |
| Directory fixture | 102,400 | 26 | Tree shape plus streaming content | 18.728 ms | 20.661 ms |

Metadata-only checks are reported separately from content verification. These results show scaling on controlled fixtures and are not universal latency guarantees; storage cache, filesystem, file count, content size, and antivirus activity affect them.

The Phase 3 performance regression used 2,000 warm samples. Full direct interpretation measured **0.0389 ms p50 / 0.0937 ms p95**, paraphrase **0.0450 / 0.0721 ms**, and Hinglish **0.0369 / 0.0614 ms**. The proposed 0.05 ms p50 / 0.10 ms p95 warm interpretation objective remained satisfied in this run.

At the Phase 4 sample point ARIA used **34.89 MiB RSS**, **0.0% of one logical CPU** over a one-second idle interval, and **one process**. The Python source tree is 162,924 bytes, an increase of 26,820 bytes from the Phase 3 baseline. `pyproject.toml` grew by 76 bytes only to declare the opt-in test marker. `uv.lock` stayed at 69,699 bytes with the same SHA-256, so production dependency size changed by **0 bytes** and no dependency was added.

## Acceptance

Phase 4 acceptance is satisfied:

- every filesystem action enters through `Engine` validation, fixed risk, confirmation where required, final identity recheck, execution, and verification;
- no destructive action accepts an implicit, ambiguous, changed, or unreliable target;
- destination collisions never overwrite;
- on-disk success is verified for create/copy/move/rename, and operations that cannot prove the complete requested effect remain explicit `UNVERIFIED`;
- verified recent state, five-minute expiry, rollback/recovery data, and failure isolation pass;
- the complete Phase 0–3 regression suite remains green;
- interpretation performance and single-process idle behavior remain lightweight.

Environment-dependent gaps and deliberate exclusions are recorded in [phase4-limitations.md](phase4-limitations.md).

