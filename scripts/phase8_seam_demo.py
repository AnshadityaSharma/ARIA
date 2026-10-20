"""Run an isolated, execution-free native Seam demo with the existing Python env."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aria.shard_presentation import DisplayEvent, DisplayState as S, OutcomeStatus
from aria.seam_presentation import ActivityEvent, ActivityKind
from aria.seam_windows import enable_standalone_dpi
from aria.seam_ui import SeamWindow


class SyntheticSource:
    def __init__(self, adapter):
        self.adapter = adapter
        self.serial = 0
        self.session = None
        self.sequence = -1

    def start(self):
        previous = self.session
        self.serial += 1
        self.session = f"synthetic-{self.serial}"
        self.sequence = 0
        return self.adapter.submit(DisplayEvent(self.session, 0, S.LISTENING, supersedes=previous))

    def send(self, state, text=None, revision=None):
        self.sequence += 1
        outcome = OutcomeStatus(state.value) if state in {S.VERIFIED, S.UNVERIFIED, S.FAILED, S.CANCELLED} else None
        return self.adapter.submit(DisplayEvent(self.session, self.sequence, state, revision, text, outcome))

    def show(self, state, long=False):
        self.start()
        if state == S.IDLE:
            self.send(S.CANCELLED)
            self.send(S.IDLE)
            return
        if state == S.LISTENING:
            return
        self.send(S.PARTIAL, "Move the current window", 0)
        if state == S.PARTIAL:
            return
        text = ("Move this window to the right. " * 60).strip() if long else "Move this window to the right"
        self.send(S.FINAL, text, 1)
        if state == S.FINAL:
            return
        if state in {S.FAILED, S.CANCELLED}:
            self.send(state)
            return
        self.send(S.PROCESSING)
        if state == S.PROCESSING:
            return
        if state == S.CONFIRMATION:
            self.send(state)
            return
        self.send(S.EXECUTING)
        if state != S.EXECUTING:
            self.send(state)


def main():
    enable_standalone_dpi()
    root = tk.Tk()
    root.title("ARIA Seam — synthetic events only")
    root.geometry("560x390+30+320")
    ui = SeamWindow(root)
    source = SyntheticSource(ui.adapter)
    token = [0]
    def play(state, long=False):
        token[0] += 1
        source.show(state, long)
    def quick():
        token[0] += 1
        current = token[0]
        source.start()
        def finish():
            if current == token[0]:
                source.send(S.FINAL, "Open Chrome", 0)
                source.send(S.EXECUTING)
                source.send(S.VERIFIED)
        root.after(650, finish)
    def envelope(kind):
        import math
        token[0] += 1
        current = token[0]
        source.show(S.VERIFIED if kind == ActivityKind.OUTPUT else S.LISTENING)
        session = source.session
        def sample(n=0):
            if current != token[0] or ui.closed:
                return
            level = .55+.35*math.sin(n*.7) if n < 28 else 0.
            ui.adapter.submit_activity(ActivityEvent(session, n, kind, level))
            if n < 28:
                root.after(70, lambda: sample(n+1))
        sample()
    ttk.Label(root, text="ARIA · Seam", font=("Segoe UI", 16)).pack(pady=(14, 4))
    ttk.Label(root, text="Presentation only. No microphone or command execution.").pack()
    bar = ttk.Frame(root)
    bar.pack(fill="x", padx=14, pady=10)
    ttk.Button(bar, text="Quick command", command=quick).pack(side="left")
    ttk.Button(bar, text="Synthetic listening", command=lambda: envelope(ActivityKind.INPUT)).pack(side="left")
    ttk.Button(bar, text="Synthetic speaking", command=lambda: envelope(ActivityKind.OUTPUT)).pack(side="left")
    states = ttk.Frame(root)
    states.pack(fill="x", padx=14)
    for i, state in enumerate(S):
        ttk.Button(states, text=state.value.title(), command=lambda s=state: play(s)).grid(row=i//3, column=i%3, sticky="ew", padx=3, pady=3)
    footer = ttk.Frame(root)
    footer.pack(fill="x", padx=14, pady=12)
    ttk.Button(footer, text="Long transcript", command=lambda: play(S.FINAL, True)).pack(side="left")
    ttk.Button(footer, text="Inspect", command=lambda: ui.expand(True)).pack(side="left")
    def reduced():
        ui.reduced_motion = not ui.reduced_motion
        ui.preference_override = (ui.high_contrast, ui.reduced_motion)
        ui.adapter.last_frame = None
    ttk.Button(footer, text="Reduced motion", command=reduced).pack(side="left")
    def contrast():
        ui.high_contrast = not ui.high_contrast
        ui.preference_override = (ui.high_contrast, ui.reduced_motion)
        ui.adapter.last_frame = None
    ttk.Button(footer, text="High contrast", command=contrast).pack(side="left")
    def close():
        token[0] += 1
        ui.close()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    main()
