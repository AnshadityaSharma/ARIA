# Baseline benchmark method

Run `python scripts/voice_benchmark.py <audio.wav>` after the local model is cached. It reports model-load time, warm transcription latency, confidence/language, process RSS, CPU time, and audio duration. Interactive voice mode separately reports capture, ASR, parse/dispatch, action, and end-to-end timings for each command.

Results are machine- and microphone-specific. Do not treat committed measurements as guarantees.

## 2026-09-22 Sprint 2 baseline

Windows 11, Intel 10th-generation CPU, CPU `int8`, multilingual `base`, synthetic 1.644 s “Open Camera” WAV:

- one-time download plus first model load: 290,188.670 ms
- cached process model load: 2,047.336 ms
- cached transcription: 1,799.909 ms (real-time factor 1.095)
- confidence: 0.514; detected language: English
- resident memory after transcription: 236.9 MB
- process CPU time for transcription: 6.281 s

The interactive controller retains the loaded model, so its steady-state commands avoid the recorded 2.047 s process-load cost. Microphone duration and action time still contribute to end-to-end latency.

## Sprint 3 desktop baseline — 2026-09-22

Command: `python scripts/desktop_benchmark.py --acceptance`. Windows 11 build 26200,
Intel Family 6 Model 165, 16 logical CPUs; multilingual base, CPU int8.
The four command WAVs are Windows-synthesized speech. Hotkey delivery, UI, Camera,
confirmation buttons, and Recycle Bin operations are real. Generated raw results:
`logs/desktop-baseline.json` (ignored by Git).

| Measurement | Observed |
| --- | ---: |
| Desktop/model startup | 1,635 ms |
| Idle RSS (3-second sample) | 206.82 MB |
| Idle process CPU | 3.1% |
| Real microphone startup | 233.98 ms |
| Microphone smoke | 1,600 frames; no overflow |
| Injected hotkey → delivery | 1.43–2.00 ms |
| Delivered hotkey → listening UI | 13.67–39.96 ms |
| ASR | 1,506–1,932 ms |
| Parse | 0.17–0.96 ms |
| Low-risk decision | 0.043–0.061 ms |
| Active RSS samples | 272.88–274.44 MB |
| Active process CPU | 178.4–392.9% |
| Camera launch/verification | 2,067 ms |
| Native move | 10.45 ms |
| Constrained resize/readback | 199–210 ms |

CPU uses psutil's process convention: 100% is one logical CPU. Here 3.1% is about
0.19% of total logical capacity; 392.9% is about 24.6%. RSS is a sample, not a
guaranteed peak. These are single-run observations, not percentile guarantees.

Hotkey → action complete: Open Camera 3,677 ms; 20% resize 2,178 ms; top-right move
1,555 ms; relative shrink 1,846 ms. Live speech duration is excluded because audio
was pre-generated. Camera constrained both resizes; see `sprint3.md`.

Structured confirmation fixture: hotkey → dialog 40.78–48.47 ms;
Confirm response → action start 1.76 ms; response → completed Recycle Bin operation
115.48 ms. Cancel preserved the file. These figures exclude user deliberation time.

Logs record hotkey receipt, rendered listening state, microphone request/ready,
speech endpoint detection, ASR start/end, parse, risk decision, confirmation
shown/answered, and action start/end. Unreached milestones on failures are omitted.

## Sprint 4 browser benchmark

Run python scripts/browser_benchmark.py. It launches real Playwright Chromium
against a deterministic loopback page and reports lazy engine initialization, process
tree RSS/CPU without and with Chromium, startup/navigation/interaction/download
latencies, download verification, and post-close child-process count. Generated raw
results are written to logs/browser-baseline.json and are intentionally ignored.

### 2026-09-22 Sprint 4 local browser baseline

Windows 11 build 26200, Python 3.12.10, Playwright Chromium 153, headless, loopback
HTTP page. CPU follows psutil's process convention and is a one-second sample.

| Measurement | Observed |
| --- | ---: |
| Lazy engine construction | 0.058 ms |
| Without browser | 1 process; 30.53 MB RSS; 0.0% CPU |
| Browser startup | 803.464 ms |
| First launch plus navigation | 835.029 ms |
| With browser idle sample | 6 processes; 319.40 MB RSS; 14.2% CPU |
| Warm navigation | 19.371 ms |
| Accessible field fill | 47.875 ms |
| Confirmed local form submit | 85.825 ms |
| Download and disk verification | 305.438 ms |
| After close | 1 process; 40.14 MB RSS |

The live YouTube smoke also passed in 11.78 seconds during one run. That includes
browser launch, two YouTube navigations, result discovery, selection, and playback
verification. Repeated runs varied because ads/media delivery sometimes left the
correct watch page paused; the external smoke reports that condition separately. The
successful observation is not a stable latency target.
