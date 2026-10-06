# Phase 2 Windows discovery and control contract

`context.md` is authoritative. This document records the Phase 2 implementation boundary. Phase 0's frozen corpus and evaluation method are unchanged, and Phase 2 does not change natural-language grammar or introduce learned interpretation.

## Discovery and resolution

Installed applications come from Windows `Get-StartApps` records. Every `(Name, AppID)` record is retained, including duplicate display names. Resolution is deterministic: normalized exact display name first, then a unique display-name substring. Missing and multiple matches fail closed. Results are cached for two seconds to avoid repeatedly starting PowerShell; expiry or a new `Applications` instance refreshes discovery, and Engine forces a fresh registration recheck immediately before launch. No production application catalogue exists.

Visible top-level windows are enumerated dynamically. A stable identity contains HWND, PID, and process creation time. Snapshots also retain title, executable path, application identity when Windows exposes it, geometry, and normal/minimized/maximized placement. Named resolution tries exact title, exact executable/application identity, then conservative substring. Distinct matches fail as ambiguous. Repeated enumeration of the same HWND is deduplicated as one identity.

Tracked `it`/`that`, explicit names, and foreground targeting retain their existing meaning. Once stable identity is stored, a missing or changed target cannot fall back to a different window.

## Guarded execution and verification

All application and window actions enter through `Engine`; the Phase 1 validation, fixed risk, confirmation, target-recheck, execution, and verification boundary remains authoritative. The Windows adapter is an internal executor rather than a second entry point.

Application launch resolves and rechecks the exact discovered AppID, captures pre-launch stable identities and foreground identity, then correlates a new window by application identity/name/executable or a unique new-window delta. Multiple candidates fail closed. ARIA tracks only the verified correlated window.

Before a window mutation, Engine resolves the target and `WindowManager.recheck` compares HWND, PID, and process creation time. A vanished HWND, reused HWND, PID/process mismatch, or identity that Windows cannot establish fails closed. Focus verifies the foreground HWND. Minimize, maximize, and restore verify placement. Move and resize read back stable geometry, report application/Windows constraints, and verify identity again. Move and resize restore minimized/maximized targets before applying geometry. Relative resize and monitor-relative positions use the observed current rectangle and the target monitor work area. Tracked state changes only after successful stable-window verification in the production path.

`OPEN_PATH` resolves an existing absolute or known-folder path, rechecks its filesystem identity immediately before dispatch, and reports `UNVERIFIED` after Windows accepts the request because Phase 2 cannot reliably correlate every folder/file handler UI. It never claims a verified window. Known folders use Windows Known Folder IDs rather than fixed user-directory strings.

## Reproduction

Controlled suite:

    .venv\Scripts\python.exe -m pytest -q

Native disposable Windows suite:

    $env:ARIA_WINDOWS_INTEGRATION='1'
    .venv\Scripts\python.exe -m pytest -q tests\test_windows_integration.py -k "disposable_native or vanished_native or generated_start_app or second_monitor"

Measurements:

    .venv\Scripts\python.exe scripts\phase2_windows_benchmark.py --iterations 10 --launch-iterations 3 --output docs\phase2-measurements.json

The native suite owns its Tk windows. Its dynamic-application test creates a UUID-named Start Menu shortcut to a disposable fixture, discovers it through Windows, launches its exact AppID through Engine, verifies the resulting window, and removes the shortcut/window. No generated application name is present in production code. The live second-monitor test runs only when another monitor is connected; controlled tests always cover negative-coordinate work areas.
