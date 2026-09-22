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
