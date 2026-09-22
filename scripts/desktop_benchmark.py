"""Reproducible local desktop benchmark. Synthetic speech; real UI and executors.

Run with --acceptance to open/resize Camera temporarily. No user speech is recorded.
Generated WAVs and results stay in ignored logs/. Actual microphone startup is measured
with a separate 100 ms capture whose samples are discarded.
"""
import argparse
import ctypes
import json
import logging
from pathlib import Path
import platform
import subprocess
import time

import psutil

from aria.ui import DesktopApp
from aria.voice import LocalASR, Microphone, VoiceController


class FixtureMicrophone:
    def __init__(self, files):
        self.files = iter(files)
    def capture(self):
        from faster_whisper import decode_audio
        return decode_audio(str(next(self.files)))


def press_ctrl_space():
    u32 = ctypes.windll.user32
    u32.keybd_event(0x11, 0, 0, 0)
    u32.keybd_event(0x20, 0, 0, 0)
    u32.keybd_event(0x20, 0, 2, 0)
    u32.keybd_event(0x11, 0, 2, 0)


def pump_until(app, condition, timeout=30):
    deadline = time.monotonic()+timeout
    expired = []
    def check():
        if condition():
            app.root.quit()
        elif time.monotonic() >= deadline:
            expired.append(True)
            app.root.quit()
        else:
            app.root.after(10, check)
    app.root.after(0, check)
    app.root.mainloop()
    if expired:
        raise TimeoutError("Desktop benchmark timed out")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--acceptance", action="store_true")
    args = parser.parse_args()
    output = Path("logs")
    output.mkdir(exist_ok=True)
    logging.basicConfig(filename=output/"desktop-benchmark.log", level=logging.INFO)
    phrases = ["Open Camera", "Make it one fifth of the screen",
               "Move it to the top right", "Make it 10 percent smaller"] if args.acceptance else ["take screenshot"]
    files = [output / f"desktop-benchmark-{i}.wav" for i in range(len(phrases))]
    # Fixed local synthesis inputs, never user commands or shell-interpolated paths.
    for phrase, file in zip(phrases, files):
        script = ("Add-Type -AssemblyName System.Speech; "
                  "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  f"$s.SetOutputToWaveFile('{file.resolve()}'); "
                  f"$s.Speak('{phrase}'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=15)
    process = psutil.Process()
    report = {"platform": platform.platform(), "cpu": platform.processor(),
              "logical_cpus": psutil.cpu_count(), "audio_source": "local Windows synthetic speech"}
    started = time.perf_counter()
    def voice_factory(engine):
        return VoiceController(engine, microphone=FixtureMicrophone(files), asr=LocalASR("base"))
    app = DesktopApp(voice_factory=voice_factory)
    before_windows = app.engine.windows.windows()
    original = {w.handle: w.rect for w in before_windows}
    try:
        pump_until(app, lambda: app.hotkey is not None or "Error" in app.label.cget("text"), 60)
        if app.controller is None or app.hotkey.error:
            raise RuntimeError(app.label.cget("text"))
        report["startup_ms"] = round((time.perf_counter()-started)*1000, 3)
        process.cpu_percent(None)
        app.root.after(3000, app.root.quit)
        app.root.mainloop()
        report["idle_rss_mb"] = round(process.memory_info().rss/1048576, 2)
        report["idle_cpu_percent"] = process.cpu_percent(None)
        import sounddevice as sd
        mic_start = time.perf_counter()
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32") as stream:
            report["microphone_startup_ms"] = round((time.perf_counter()-mic_start)*1000, 3)
            data, overflow = stream.read(1600)
            report["microphone_smoke"] = {"frames":len(data), "overflow":overflow}
        results = []
        for phrase in phrases:
            old = app.controller.last_timeline
            process.cpu_percent(None)
            cpu_before = process.cpu_times()
            press_start = time.perf_counter()
            press_ctrl_space()
            pump_until(app, lambda: app.controller.last_timeline is not old, 45)
            line = app.controller.last_timeline
            cpu_after = process.cpu_times()
            results.append({
                "phrase":phrase, "status":app.controller.last_status,
                "timings_ms":line.milliseconds(),
                "event_offsets_ms":{key:round((value-line.events["hotkey_press"])*1000,3) for key,value in line.events.items()},
                "injection_to_hotkey_ms":round((line.events["hotkey_press"]-press_start)*1000,3),
                "active_rss_mb":round(process.memory_info().rss/1048576,2),
                "active_cpu_percent":process.cpu_percent(None),
                "active_cpu_seconds":round(cpu_after.user+cpu_after.system-cpu_before.user-cpu_before.system,3),
            })
            pump_until(app, lambda: not app.controller.busy, 5)
        report["commands"] = results
        # Exercise confirmation via the real hotkey, dialog, and guarded engine.
        # This fixture supplies a structured action; it is not an ASR measurement.
        from aria.core import Action, ActionType
        from aria.voice import Transcript
        target = output / "aria_confirmation_benchmark.txt"
        target.write_text("Disposable ARIA benchmark file", encoding="utf-8")
        class ConfirmationVoice:
            def prepare(self, line, on_state):
                on_state("LISTENING")
                line.mark("microphone_start")
                on_state("PROCESSING")
                line.mark("asr_start")
                line.mark("transcription_complete")
                line.mark("command_parse")
                line.events["parse_complete"] = line.command_parse
                return Transcript("structured fixture", 1, "en", 1), Action(ActionType.DELETE_PATH, str(target.resolve())), line
        original_voice = app.controller.voice
        confirmation_results = []
        try:
            app.controller.voice = ConfirmationVoice()
            for answer in ("cancelled", "confirmed"):
                old = app.controller.last_timeline
                previous_dialog = app.dialog
                press_ctrl_space()
                pump_until(app, lambda: app.dialog is not None and app.dialog is not previous_dialog, 5)
                if answer == "confirmed": app.dialog.confirm_button.invoke()
                else: app.dialog.cancel_button.invoke()
                pump_until(app, lambda: app.controller.last_timeline is not old, 5)
                confirmation_results.append({"response":answer, "file_exists_after":target.exists(),
                    "timings_ms":app.controller.last_timeline.milliseconds(),
                    "source":"structured-action fixture; real hotkey, UI buttons, and file executor"})
                pump_until(app, lambda: not app.controller.busy, 5)
            report["confirmation"] = confirmation_results
        finally:
            app.controller.voice = original_voice
        report["acceptance_passed"] = (
            all(row["status"][0] == "SUCCESS" for row in results)
            and confirmation_results[0]["file_exists_after"]
            and not confirmation_results[1]["file_exists_after"]
        )
        print(json.dumps(report, indent=2), flush=True)
        # Generated report artifact, not source code.
        (output / "desktop-baseline.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if not report["acceptance_passed"]:
            raise RuntimeError("Desktop acceptance failed; inspect the saved report")
    finally:
        handle = app.engine.state.handle
        if handle and app.engine.windows.exists(handle):
            if handle in original:
                app.engine.windows.place(handle, original[handle])
            else:
                ctypes.windll.user32.PostMessageW(handle, 0x10, 0, 0)
        app.close()


if __name__ == "__main__":
    main()
