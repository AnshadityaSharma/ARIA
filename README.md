# ARIA

ARIA (Adaptive Runtime Intelligence Assistant) is a local-first, latency-first Windows automation system. Sprint 1 provides a deterministic text-command fast path: dynamic application discovery, native window control, filesystem capabilities, screenshots, volume control, action validation/risk metadata, logging, and minimal tracked-window state.

No LLM, voice system, browser agent, or cloud API is used.

## Setup

```powershell
uv sync --dev
uv run aria
```

Type `help` in the interactive prompt. Run tests with `uv run pytest`.

Architecture and scope are documented in `context.md` and `docs/architecture.md`.

