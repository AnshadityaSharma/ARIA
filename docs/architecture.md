# Sprint 1 architecture

Text is parsed into a validated `Action`. The engine applies deterministic risk metadata, dispatches to a narrow desktop capability, verifies observable results, and returns a `Result`. Windows-specific code is isolated in `windows.py` and `desktop.py`.

Applications are discovered from Windows Start Apps at runtime; there is no application catalogue. Known folders use Windows Known Folder APIs rather than constructed user paths.

The only session state is a window handle, title, and current geometry. Successful focus/move/resize/show operations refresh it. Pronouns resolve to this window; if it is invalid, the foreground window is used. A generic conversational state system remains Phase 2.

