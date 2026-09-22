# Sprint 1 architecture

Text is parsed into a validated `Action`. The engine applies deterministic risk metadata, dispatches to a narrow desktop capability, verifies observable results, and returns a `Result`. Windows-specific code is isolated in `windows.py` and `desktop.py`.

Applications are discovered from Windows Start Apps at runtime; there is no application catalogue. Known folders use Windows Known Folder APIs rather than constructed user paths.

Sprint 1 began with a window handle, title, and current geometry. Successful focus/move/resize/show operations refresh it. Sprint 2 extends this state narrowly as described below.

## Sprint 2 state and voice

State now also retains previous geometry and last window action. `it` and `that` strictly require the tracked window; a vanished target produces a clear error instead of silently acting elsewhere. `this window` explicitly selects the foreground window and makes it the new tracked target after success.

Push-to-talk capture produces 16 kHz mono audio and stops after post-speech silence. One persistent multilingual faster-whisper model transcribes locally, then the existing deterministic parser and executor handle the command. Low-confidence or empty speech is rejected before parsing or execution. No transcript or audio is uploaded for inference.
