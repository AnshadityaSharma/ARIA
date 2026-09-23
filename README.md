# ARIA

ARIA (Adaptive Runtime Intelligence Assistant) is a local-first, latency-first Windows automation system. Sprint 1 provides a deterministic text-command fast path: dynamic application discovery, native window control, filesystem capabilities, screenshots, volume control, action validation/risk metadata, logging, and minimal tracked-window state.

The deterministic desktop core is independent of speech recognition.

Sprint 2 added local voice input. Sprint 3 added a global hotkey, status overlay,
and action-bound confirmations. Sprint 4 adds a lazy persistent Playwright browser
for deterministic navigation, search, accessible interaction, YouTube playback, and
verified downloads. No cloud inference or LLM is used.

## Setup

```powershell
uv sync --dev
uv run playwright install chromium
uv run aria
```

Type `help` in the interactive prompt. Start local push-to-talk mode with `uv run aria --voice`; press Enter, speak a short command, then pause. The multilingual model is downloaded once and all transcription then runs locally. Run tests with `uv run pytest`.

Architecture and scope are documented in `context.md` and `docs/architecture.md`.

Browser examples include open YouTube, search YouTube for Blinding Lights, play
Blinding Lights, open example.com, type hello in Search, click button Continue, and
download Test file. Browser controls use accessible names, not CSS selectors or
screen coordinates.

## Desktop mode (Sprint 3)

```powershell
.\.venv\Scripts\aria.exe --desktop
```

Press **Ctrl+Space**, speak one command, then pause. The overlay shows listening,
processing, execution, confirmation, success, and errors. Repeat hotkeys are ignored
until the active command finishes. Use Quit to unregister the hotkey.

Medium/high-risk commands open a Cancel/Confirm dialog. Its default timeout is
30 seconds; configure it with `--confirmation-timeout 45`. To confirm low-risk
operations too, use `--confirm-low`. Closing or timing out the dialog executes nothing.

Desktop mode uses the already-cached multilingual `base` model and keeps it loaded.
If the cache is absent, explicitly provision the weights once:

```powershell
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
```

This provisioning step downloads model weights. Interactive inference uses local
files only. See `docs/sprint3.md` for validation scope and known limitations.
