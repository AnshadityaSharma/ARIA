# Sprint 5 — Phase 7 local intent fallback

## Status — 2026-09-23

Implementation and non-model regression testing are complete. **Real-model acceptance
is blocked, not passed.** Windows Application Control refuses to load the downloaded
llama-server-impl.dll (WinError 4551). The official download checksum matches, but
a checksum does not override OS approval. The user explicitly instructed us not to
disable, weaken, bypass, or replace the blocked native runtime with another
unapproved runtime. No such workaround is included.

The first real-model command failed at runtime startup. Consequently model load time,
warm/cold inference latency, loaded RSS/CPU, token counts, intent accuracy, schema-valid
rate, invalid-output rate, unsupported-action rate and model fallback rate are
**not measured**. Do not substitute mocked test results for these metrics.

No Sprint 5 commit or push has been made: real-model acceptance remains outstanding.
The prior completed commit is 5ae19946e0ba2ed50ef1dc2d1128cb1a809a6618.

## Provisional model/runtime selection

This is a specification-based shortlist, not a measured comparison. Only one model
was downloaded. No candidate has passed the local real-inference acceptance gate.

| Candidate | Size/license and language evidence | Decision/tradeoff |
| --- | --- | --- |
| Qwen2.5-0.5B-Instruct GGUF | 0.49B parameters, Apache-2.0; multilingual/JSON instruction model | Smaller capacity/weight footprint is attractive; short-command quality and CPU latency unmeasured |
| Qwen2.5-1.5B-Instruct GGUF | 1.54B parameters, Apache-2.0; official quantizations and JSON/multilingual focus | Provisional choice: more capacity with a roughly 1.1 GB Q4_K_M file; no proven laptop latency/RAM claim |
| SmolLM2-1.7B-Instruct | 1.7B parameters, Apache-2.0; primarily English | Viable compact alternative, less aligned with exploratory Hinglish; quantized Windows packaging would need separate validation |

Sources: [Qwen 0.5B card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF),
[Qwen 1.5B card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF),
[SmolLM2 card](https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct).
Published JSON/language capabilities are not measured ARIA accuracy. Indian-English
and Hinglish examples are in the development corpus; no accent/audio claim is made.

Selected file: qwen2.5-1.5b-instruct-q4_k_m.gguf, **1,117,320,736 bytes**
(1.117 GB / 1,065.56 MiB), Q4_K_M mixed quantization. Runtime RAM includes additional
context/cache/working buffers; file size is not an RSS estimate.
Pinned model revision: 91cad51170dc346986eccefdc2dd33a9da36ead9.
SHA-256: 6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e.

Runtime: [llama.cpp CPU Windows x64, b11126](https://github.com/ggml-org/llama.cpp/releases/tag/b11126).
Native quantized inference plus grammar-constrained JSON avoids adding a Python ML
framework. Python communicates only with its owned loopback process using the standard
library. No Python dependencies or lockfile changes. The downloaded runtime archive
is 18,558,051 bytes; SHA-256
88b6648aa8a96c751a5279cff96ad79cb6070bc3ef2b4f77fc10ea4c29909d1c.
For distribution, retain the upstream runtime/model licenses and bundled notices.
Windows approval of the native DLLs is an unresolved packaging requirement.

## Architecture and scope

Text and voice reach the same Interpreter and existing Engine. The deterministic
parser is tried first; only ParseError can request model interpretation. Deterministic
validation errors do not retry through a model. No model process or weights are
loaded at startup, and ordinary commands never invoke it. Fallback is opt-in via
--intent-model; default installations retain deterministic-only behavior.

The model returns one object with exactly action, target and params, or the explicit
uncertainty object {"status":"uncertain"}. There is no numeric model confidence:
this model/runtime does not provide a calibrated confidence signal. Grammar-constrained
output is defense in depth, not a replacement for validation. JSON fences, duplicate
keys, NaN, missing/extra fields, unsupported actions, invalid parameter types/ranges,
invented targets, and incomplete/token-limited generations are rejected. Literal
targets must occur in the command. This conservative grounding may reject a useful
spelling correction; it does not enumerate installed applications.

The exposed capability subset uses actual ActionType values and the existing RISK
registry: OPEN_APPLICATION, FOCUS_WINDOW, MINIMIZE_WINDOW, MAXIMIZE_WINDOW,
RESTORE_WINDOW, MOVE_WINDOW, RESIZE_WINDOW, OPEN_PATH, OPEN_BROWSER, OPEN_WEBSITE,
SEARCH_WEB, SEARCH_YOUTUBE, PLAY_YOUTUBE, DELETE_PATH. No invented FOCUS_APPLICATION,
OPEN_FOLDER, or OPEN_FILE variants. The last capability verifies that even a model
interpretation of deletion still reaches the existing HIGH-risk confirmation gate.
All other deterministic capabilities remain available on the existing parser path.

Window references are tracked or foreground; the engine still owns geometry/history,
missing-window behavior and the hotkey-captured foreground handle. The model receives
no window catalogue, page content, screenshots, tools or execution handles. Dynamic
application discovery and browser target resolution remain unchanged.

Conservative prechecks reject vague open/deletion targets, explicit unsupported
command categories and obvious multi-action instructions. Existing browser search/
typing payloads remain data, not executable instructions. These checks are not a
general natural-language security classifier. A schema-valid interpretation can
still be semantically wrong; real quality evaluation is mandatory before release.

The sample "Open the browser and look up Python decorators" conflicts with the
one-action requirement: these are two existing actions. It deliberately asks the
user to split the request. It neither invents a combined action nor silently executes
half the request. This is an expected rejection in the corpus and smoke acceptance.

## Lifecycle and limits

One lazy owned llama-server process is reused across fallback commands. CPU-only
(-ngl 0), four threads, context 2048, temperature 0, fixed seed, one request slot,
and 128 output tokens by default. Loading timeout defaults to 60 seconds; inference
timeout to 20 seconds. Request and response sizes are bounded. The input limit is
1024 characters; a long tokenized prompt can still exceed context and must fail closed.

The server is bound to 127.0.0.1 with a random per-instance API key. Offline,
no-webui, no-agent and no-slots options are explicitly passed. No remote endpoint
is configurable. Downloads happen only in the explicit provisioning script, never
during inference. A timeout kills and waits for the owned process; another explicit
command may cold-load again, but there is no automatic retry. Quit closes the
runtime before waiting for the desktop worker. Model load/start/complete/timeout
events extend the existing voice timeline; metrics are logged without transcript text.

This runtime protocol/flag combination still needs validation on an approved native
installation. The implementation has mock protocol, real inert-process cancellation,
startup failure, close-in-flight, and cleanup tests; these are not native model tests.

## Installation and reproduction

Do not run the blocked runtime again on this machine until an approved installation
is supplied. Do not change Windows protection or try a different unapproved binary.

On a machine where the runtime is explicitly approved, the separate one-time
provisioning command is: uv run python scripts/provision_intent.py.
It downloads the pinned official archive and single GGUF, verifies both SHA-256
hashes and keeps them under the ignored .aria-runtime directory. It does not change
machine security policy. No model weights, native binaries, or generated logs belong
in Git.

After approval, enable fallback with:
uv run aria --intent-model .aria-runtime/qwen2.5-1.5b-instruct-q4_k_m.gguf
and optionally --desktop or --voice. An approved compatible installation can be
selected with --intent-runtime C:/approved/path/llama-server.exe.
Limits: --intent-timeout 20 --intent-load-timeout 60 --intent-max-tokens 128.

Without any model execution:
uv run python scripts/intent_benchmark.py --skip-model --output logs/intent-fast-path-baseline.json.

Only after runtime approval:
uv run python scripts/intent_benchmark.py --runtime C:/approved/path/llama-server.exe.
This uses the fixed 27-case tests/data/intent_eval.json corpus. It compares the
unmodified deterministic parser with fallback, records actual model output/token/
timing/resource data, and passes correctly interpreted actions through the real
Engine with controlled adapters (no uncontrolled apps, browser or file operations).
Failed infrastructure is reported as blocked, not as model accuracy. The corpus
is a development set, not a held-out quality guarantee; uncertainty is separate
from schema-valid actions.

## Verification and remaining gate

Full opt-in regression run: **157 passed**, including live YouTube and all Windows/
desktop/local-browser checks. Five pre-existing sounddevice/NumPy deprecation
warnings were emitted. Focused intent suite: **68 passed**, no model download or
native llama.cpp execution required. Dependency manifests/lockfile are unchanged;
Python compilation and CLI help checks passed. Weights/runtime are ignored by Git.

Mock tests cover output validation, deterministic preference, lazy loading/reuse,
timeout cancellation, crash/unavailable cases, shutdown cleanup, voice routing,
dynamic targets, tracked-window loss, and HIGH-risk output confirmation.
Real Windows tests cover isolated disposable native window geometry on both parser
and mocked-model paths, microphone capture, hotkeys and confirmation dialogs.
Existing local Chromium and live YouTube checks also run.

A previous native-window test selected a minimized existing Notepad window. It now
owns a uniquely named disposable Tk window and never selects or closes user Notepad.
One full run encountered a transient Tk script-read failure; the file existed, the
isolated checks passed, and the unchanged subsequent full suite passed.

Remaining: obtain an approved native runtime, run all five smoke inputs (four
controlled actions and the documented compound rejection), run the full corpus and
resource benchmark, review measured suitability, then repeat regressions and the
commit/push gate. No Phase 8 router, agent, vision, cloud API or training is included.
