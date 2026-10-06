# Phase 4 limitations

- `OPEN_PATH` can prove that Windows accepted the request, but it cannot deterministically correlate a resulting Explorer or application window. It therefore remains `UNVERIFIED` and does not update `FileState`.
- Recycle Bin deletion observes that the source path disappeared, but the standard library mechanism does not expose a stable identity for the new Recycle Bin entry. The result remains `UNVERIFIED`; restore verification is outside Phase 4.
- Reparse-point traversal is rejected for every filesystem mutation and currently for open-path as well. Junctions, symbolic links, cloud placeholders, UNC/network paths, device namespaces, alternate data streams, and drive-relative paths are outside this phase.
- Bare-name discovery searches exact direct children of the captured base and known folders. It intentionally avoids fuzzy matching and unbounded recursive disk scans.
- A native cross-volume move requires `ARIA_CROSS_VOLUME_ROOT` to name a disposable directory on a second volume. This machine had no such configured fixture, so native timing and integration were skipped. The controlled device-boundary test verifies copy → content verification → source removal and failure handling.
- Native symbolic-link creation was unavailable to the test account. Controlled reparse detection passed, and production rejects reparse attributes before execution.
- Stable identity and exclusive create/no-replace operations narrow time-of-check/time-of-use exposure, but Windows cannot make an arbitrary multi-step copy or cross-volume move one transaction. Any detected change fails closed or yields explicit recovery data.
- An executor-level interruption during a copy can leave a partial destination. ARIA reports failure and does not update `FileState`; it does not delete a partial path unless it has a complete observed snapshot and can prove that exact output remained unchanged.
- Streaming content hashing is used only when content equivalence is part of verification. Its cost grows with bytes and directory entries; performance results apply to the recorded fixtures and machine only.
- The language grammar is finite. It accepts explicit supported file commands and literal paths; it does not infer organization goals, search file contents, understand document meaning, or plan multi-step filesystem work.
- Phase 7, human voice evaluation, browser expansion, and any learned interpreter were not run or added.
