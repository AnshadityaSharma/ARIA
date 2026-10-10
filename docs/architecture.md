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

## Sprint 5 intent interpretation

Engine.interpret is shared by text and voice. The current `Interpreter.interpret`
calls the deterministic parser only; its optional model object is historical
experimental code and is not an active fallback. Input safety checks prevent
obvious ambiguous or compound commands from becoming generic app targets;
browser query/text payloads retain their existing literal semantics.

The model receives a capability-derived action vocabulary, not an application list.
It proposes one action or reports uncertainty. Strict JSON decoding, existing
Action.validate, additional literal-target/reference checks and the unchanged
Engine permission gate precede dispatch. The model has no executors, risk controls,
conversation memory or state mutation authority. Existing tracked-window and
browser state remain the only state systems.

The historical `LocalIntentModel` adapter was designed to own a CPU llama.cpp
process through authenticated loopback HTTP. It is not started by the current
interpreter path. No model is required for tests or default operation.

Historical model protocol tests and benchmark hooks do not establish real native
inference. Windows Application Control blocked that experiment on the development
machine; quality and resource acceptance remain pending. See sprint5.md and
benchmarks.md.

## Phase 5 hardening and planned Phase 6–9 boundaries

The later product decision removes ARIA-owned screen recording from Phase 5. Screenshot and audio actions still enter the Engine. The Phase 5 implementation binds screenshot destination and parent identity before capture, writes to a private staging file, verifies PNG decode and virtual-desktop dimensions, publishes without overwrite, and cleans only its own failed staging. Volume/mute read back actual endpoint identity and state after writing. No recorder process, recording state, FFmpeg or ffprobe enters the product. Controlled checks and one-machine native screenshot/same-state audio evidence are documented in [phase5-media.md](phase5-media.md); Phase 5 is accepted with the native-environment limitations recorded there.

Phase 6 first improves the current final-only voice pipeline using representative local real speech. `Microphone` currently uses 16 kHz mono float32/50 ms blocks and a fixed RMS endpoint; `LocalASR` transcribes after capture. A partial transcript is a versioned display event only, never an executable command. Finalization has one decision point, and partial revisions cannot produce duplicate actions. The controller/Engine remain authoritative even if the Phase 8 UI is absent.

The current `ActivationController` has one worker and `Engine.execute` holds a single execution lock through launch and window wait. Parallel independent launches are therefore a design task, not present behavior. A later bounded coordinator may hold a small dependency graph of immutable typed actions. It has no OS adapter or policy authority: every ready node passes through the Engine kernel, and successors receive only verified bound outputs. Conflicting target operations serialize; cancellation and timeouts stop dependents and expose partial outcomes. Any concurrency change must isolate application/window correlation, pending confirmations and tracked state before allowing overlapping branches. Simple single-action commands keep the direct path.

Physical pointer and keyboard commands are separate candidate capabilities. Browser DOM clicks are not desktop cursor clicks. The native action contract must bind observed foreground/window identity, pointer position or literal text/chord, deterministic risk and confirmation, target recheck, and truthful delivery versus effect verification. When an unknown UI control could have consequential effects and no safe policy can be established, abstain. The target-window always-on-top property similarly needs a distinct typed action and readback; ARIA's own overlay `-topmost` is unrelated.

Phase 8 will select an original Shard treatment with a compact floating transcript panel after comparative design. UI events carry actual listening, partial/final transcript, executing and verified outcome state. The panel coalesces frequent display updates, bounds long text, respects DPI/multiple monitors and reduced motion, and never blocks the command worker. If useful partials are unavailable, it shows listening followed by the final transcript. Phase 9 browser recipes use the bounded coordinator only after its gate; the existing in-memory Playwright context does not imply persistence across restart or reuse of the user's unrelated browser profile.
