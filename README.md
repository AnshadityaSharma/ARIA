# ARIA

ARIA (**Adaptive Runtime Intelligence Assistant**) is a local-first, low-latency Windows assistant for bounded text and voice computer commands. It uses deterministic interpretation by default, discovers applications and targets dynamically, and sends every action through one typed safety and verification boundary.

The authoritative product specification is [context.md](context.md). Older sprint documents preserve implementation history and measurements; they do not override the current roadmap.

## Product principles

- Use the simplest mechanism that reliably solves the problem.
- Keep core operation local and available offline after setup.
- Keep simple commands extremely fast and lightweight.
- Discover applications, windows, files, and other targets instead of maintaining a hardcoded application catalogue.
- Represent work as typed actions with centralized validation, deterministic risk, confirmation, target recheck, execution, and verification.
- Fail closed when a consequential target is ambiguous, changed, or unverifiable.
- Add learned interpretation only when held-out evidence shows that deterministic mechanisms are insufficient.
- Keep open-ended agent research separate from the routine-command path.

```text
deterministic interpretation
→ typed action
→ validation
→ deterministic risk
→ confirmation when required
→ target recheck
→ execution
→ verification
```

## Current status

Roadmap Phases 0–4 are accepted:

- reproducible evaluation contracts and held-out command measurement;
- a guarded execution and confirmation kernel;
- dynamic Windows application/window discovery and verified control;
- stateful deterministic English, Indian English, and bounded Hinglish command handling;
- guarded filesystem create, open, copy, move, rename, and Recycle Bin operations.

Phase 5 screenshot and volume/audio readback hardening is accepted with documented limitations. Controlled failures, native Windows 11 screenshots, and same-state speaker writes/readback support the gate; changed speaker settings, Windows 10, and physical multi-monitor behavior remain unverified. ARIA will not own screen recording or add recording dependencies. Phase 6 has an unchanged-pipeline replay harness, an opt-in no-execution live-trial runner, and a synthetic smoke, but no consented representative human-speech baseline yet; see [voice baseline evidence](docs/phase6-voice-baseline.md) and [the private corpus protocol](docs/phase6-corpus-protocol.md). Existing voice-input, engineering-overlay, and browser work must still pass the current roadmap gates before product-release claims. Bounded compound commands, physical desktop input, partial voice display, and the finished Shard are planned or gated; they are not current capabilities. No learned model is required by the product architecture.

## Planned ARIA experience

### ARIA Shard — Phase 8

ARIA will use an original **Shard** as its visual identity rather than a generic assistant orb or bubble. The Shard will normally remain hidden or minimal and appear as a lightweight Windows system presence for:

- wake detected;
- listening;
- processing;
- executing;
- success;
- error;
- confirmation required.

Phase 8 begins with a design exploration, not a predetermined final drawing. Several shapes, animations, positions, typography treatments, motion languages, and color/material approaches will be compared for uniqueness, recognizability, visual quality, accessibility, performance, implementation complexity, Windows compatibility, and logo/icon suitability. The selected presentation layer must not steal focus, obstruct work, or delay command execution.

The current engineering status overlay is not the finished Shard and does not count as Phase 8 completion.

The Phase 8 design study also includes an original compact floating transcript panel. It will show real partial words only if Phase 6 demonstrates a useful low-cost partial stream; otherwise it will show listening and the final transcript. It must never execute partial text or report success before verification.

### Selective local response voice — Phase 10

A later offline response-voice layer will be calm, concise, slightly futuristic, and restrained. Harmless commands will normally stay silent and use the Shard. Speech will be reserved for confirmation, dangerous or irreversible actions, important errors, and useful completion states.

Examples include:

- “Confirmation required.”
- “Deleting files.”
- “Closing the laptop.”

Phase 10 includes a technology evaluation based on latency, quality, runtime/model size, CPU/RAM, Windows compatibility, licensing, and offline operation. No TTS engine is selected yet. Spoken output can never authorize an action or bypass the safety kernel.

## Roadmap

| Phase | Scope | Status |
| ---: | --- | --- |
| 0 | Product contract and measurement foundation | Accepted |
| 1 | Typed execution and safety kernel | Accepted |
| 2 | Dynamic Windows discovery and control | Accepted |
| 3 | Stateful deterministic language | Accepted |
| 4 | Guarded filesystem capabilities | Accepted |
| 5 | Local media and system utilities | Accepted with documented limitations |
| 6 | Voice, activation, and bounded interaction | OPEN; evaluation tooling ready, human validation and later gates outstanding |
| 7 | Deterministic interpreter acceptance gate | Planned |
| 8 | ARIA Shard product identity and system presence | Planned, required |
| 9 | Bounded browser capabilities | Optional capability set; existing work requires validation |
| 10 | Selective local response voice | Planned |
| 11 | Distribution and daily-use reliability | Planned |
| 12 | Optional learned-interpretation experiment | Conditional on Phase 7 evidence |
| 13 | Optional open-ended task research | Separate research |

## Run the current project

```powershell
uv sync --dev
uv run aria
```

Type `help` in the interactive prompt. Run the test suite with:

```powershell
uv run pytest
```

Local push-to-talk mode is available for ongoing Phase 6 validation:

```powershell
uv run aria --voice
```

Desktop hotkey mode is an engineering interface rather than the final Shard experience:

```powershell
uv run aria --desktop
```

Optional browser development uses Playwright and may require a separately installed Chromium runtime. It is not part of the minimal desktop-command startup path.

## Documentation

- [Authoritative specification and phase gates](context.md)
- [Architecture](docs/architecture.md)
- [Phase 0 evaluation contract](docs/evaluation-contract.md)
- [Phase 1 safety kernel](docs/phase1-safety-kernel.md)
- [Phase 2 Windows contract](docs/phase2-windows.md)
- [Phase 3 deterministic language contract](docs/phase3-language.md)
- [Phase 4 filesystem contract](docs/phase4-filesystem.md)
- [Phase 5 media hardening evidence](docs/phase5-media.md)
- [Current roadmap audit, gaps and acceptance scenarios](docs/roadmap-audit.md)

The [roadmap audit](docs/roadmap-audit.md) also carries the durable handoff status
and remaining-work checklist for the next development session.

Performance figures in phase baseline documents are machine-specific measurements, not universal guarantees. Phase 7 acceptance, the Shard, local response voice, and distribution acceptance have not yet been completed.
