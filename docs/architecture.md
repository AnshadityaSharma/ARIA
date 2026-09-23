# ARIA architecture

Text is parsed into a validated `Action`. The engine applies deterministic risk metadata, dispatches to a narrow desktop capability, verifies observable results, and returns a `Result`. Windows-specific code is isolated in `windows.py` and `desktop.py`.

Applications are discovered from Windows Start Apps at runtime; there is no application catalogue. Known folders use Windows Known Folder APIs rather than constructed user paths.

Sprint 1 began with a window handle, title, and current geometry. Successful focus/move/resize/show operations refresh it. Sprint 2 extends this state narrowly as described below.

## Sprint 2 state and voice

State now also retains previous geometry and last window action. `it` and `that` strictly require the tracked window; a vanished target produces a clear error instead of silently acting elsewhere. `this window` explicitly selects the foreground window and makes it the new tracked target after success.

Push-to-talk capture produces 16 kHz mono audio and stops after post-speech silence. One persistent multilingual faster-whisper model transcribes locally, then the existing deterministic parser and executor handle the command. Low-confidence or empty speech is rejected before parsing or execution. No transcript or audio is uploaded for inference.

## Sprint 3

`GlobalHotkey` owns a native RegisterHotKey message thread (Ctrl+Space, MOD_NOREPEAT).
`DesktopApp` owns Tk on the main thread. `ActivationController` serializes capture,
transcription, permission evaluation, and execution on one worker, publishing UI
events through a queue. The model remains loaded and idle mode never opens the microphone.
The status overlay does not take focus; "this window" uses the foreground window
captured at hotkey receipt.

`PermissionEngine` returns ALLOW, CONFIRM, or DENY from the validated action and
explicit risk table. `Engine.execute` always checks permission. The boolean
`confirmed=True` API is removed. Pending actions are immutable, with an unguessable
single-use token and deadline. `Engine.confirm(token)` consumes the exact action under
a lock; file identity is checked again. New commands invalidate old requests.

Parsers return structured actions and never receive execution or approval authority.
This is an application API boundary, not an OS sandbox for hostile in-process Python.
Per-command timing records each lifecycle milestone. Native window placement is
asynchronous with bounded readback; state stores the actual OS-constrained rectangle.

## Sprint 4 browser capability

browser.py is a separate Playwright adapter reached only after the same parser,
schema validation, risk lookup, and permission gate as desktop actions. The engine
constructs it lazily, so browser packages and Chromium processes remain absent from
desktop-only startup. A persistent browser/context/page supports sequential commands;
the state holds URL, last search, and last download.

Website URLs are normalized and restricted to HTTP(S). Interactions accept
accessibility roles/names or form labels; arbitrary JavaScript and CSS selector input
are not capabilities. Downloads are saved to resolved local paths and verified.
Browser lifecycle events extend the existing timeline callback without adding a
second command system. See sprint4.md for limitations.
