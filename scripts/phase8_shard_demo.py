"""Synthetic, non-executing Tk gallery for three Phase 8 Shard directions.

Run from the repository root: python scripts/phase8_shard_demo.py
"""

from pathlib import Path
import sys
import textwrap
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aria.shard_presentation import (DisplayEvent, DisplayState, OutcomeStatus,
                                     PresentationModel)


SAMPLE = "Move the current window to the upper right, then tell me what happened."
LONG_SAMPLE = ("Move the current window to the upper right of the second monitor, "
               "keeping the full title visible and the taskbar clear. " * 5).strip()
LABELS = {
    DisplayState.IDLE: "READY", DisplayState.LISTENING: "LISTENING",
    DisplayState.PARTIAL: "HEARING · SAMPLE", DisplayState.FINAL: "TRANSCRIPT · SAMPLE",
    DisplayState.PROCESSING: "PROCESSING", DisplayState.CONFIRMATION: "CONFIRMATION",
    DisplayState.EXECUTING: "EXECUTING", DisplayState.VERIFIED: "VERIFIED RESULT",
    DisplayState.FAILED: "FAILED", DisplayState.CANCELLED: "CANCELLED",
    DisplayState.UNVERIFIED: "NEEDS ATTENTION",
}
DETAILS = {
    DisplayState.IDLE: "Ctrl + Space to speak",
    DisplayState.LISTENING: "Microphone active · no words yet",
    DisplayState.PARTIAL: "Synthetic partial · subject to revision",
    DisplayState.FINAL: "Synthetic final transcript",
    DisplayState.PROCESSING: "Interpreting final text",
    DisplayState.CONFIRMATION: "Review in the separate confirmation dialog",
    DisplayState.EXECUTING: "Waiting for an observed result",
    DisplayState.VERIFIED: "The requested effect was observed",
    DisplayState.FAILED: "The action failed",
    DisplayState.CANCELLED: "Nothing was approved in this demo",
    DisplayState.UNVERIFIED: "The effect could not be verified",
}
ACCENTS = {
    DisplayState.IDLE: "#8c9aa9", DisplayState.LISTENING: "#51dbc2",
    DisplayState.PARTIAL: "#51dbc2", DisplayState.FINAL: "#b3c3ff",
    DisplayState.PROCESSING: "#b3c3ff", DisplayState.CONFIRMATION: "#ffd386",
    DisplayState.EXECUTING: "#b3c3ff", DisplayState.VERIFIED: "#91e8ac",
    DisplayState.FAILED: "#ff9d9d", DisplayState.CANCELLED: "#c5c5cf",
    DisplayState.UNVERIFIED: "#ffd386",
}


def synthetic_snapshot(target: DisplayState, long_text: bool = False):
    """Drive the same display contract through a legal, entirely synthetic path."""
    model = PresentationModel()
    if target == DisplayState.IDLE:
        return model.snapshot
    steps = [DisplayEvent("synthetic-demo", 0, DisplayState.LISTENING)]
    if target == DisplayState.LISTENING:
        pass
    else:
        steps.append(DisplayEvent("synthetic-demo", 1, DisplayState.PARTIAL, 1,
                                  "Move the current window..."))
        if target != DisplayState.PARTIAL:
            steps.append(DisplayEvent("synthetic-demo", 2, DisplayState.FINAL, 2,
                                      LONG_SAMPLE if long_text else SAMPLE))
            if target not in {DisplayState.FINAL, DisplayState.FAILED,
                              DisplayState.CANCELLED}:
                steps.append(DisplayEvent("synthetic-demo", 3, DisplayState.PROCESSING))
            if target == DisplayState.CONFIRMATION:
                steps.append(DisplayEvent("synthetic-demo", 4, target))
            elif target == DisplayState.EXECUTING:
                steps.append(DisplayEvent("synthetic-demo", 4, target))
            elif target in {DisplayState.VERIFIED, DisplayState.UNVERIFIED}:
                steps.extend((DisplayEvent("synthetic-demo", 4, DisplayState.EXECUTING),
                              DisplayEvent("synthetic-demo", 5, target,
                                           outcome=OutcomeStatus(target.value))))
            elif target in {DisplayState.FAILED, DisplayState.CANCELLED}:
                steps.append(DisplayEvent("synthetic-demo", 3, target,
                                          outcome=OutcomeStatus(target.value)))
    for event in steps:
        if not model.apply(event):
            raise AssertionError(f"Invalid synthetic demonstration event: {event}")
    return model.snapshot


def clipped_lines(value: str, width: int = 38, limit: int = 3):
    lines = textwrap.wrap(value, width=width, break_long_words=True,
                          replace_whitespace=True) or [""]
    if len(lines) > limit:
        lines = lines[:limit]
        lines[-1] = lines[-1].rstrip(" .") + "…"
    return "\n".join(lines)


class ConceptCard(ttk.Frame):
    def __init__(self, parent, index, title, description, full_callback):
        super().__init__(parent, padding=8)
        self.index = index
        self.full_callback = full_callback
        self.snapshot = synthetic_snapshot(DisplayState.IDLE)
        self.motion_job = None
        self.canvas = tk.Canvas(self, width=360, height=320, highlightthickness=0,
                                bd=0, takefocus=0)
        ttk.Label(self, text=title, font=("Segoe UI Semibold", 14)).pack(anchor="w")
        ttk.Label(self, text=description, wraplength=345).pack(anchor="w", pady=(0, 8))
        self.canvas.pack()
        self.accessible = ttk.Label(self, text="", wraplength=340)
        self.accessible.pack(anchor="w", pady=(8, 0))
        ttk.Button(self, text="Read full transcript", command=full_callback).pack(anchor="w", pady=8)

    def render(self, snapshot, expanded, contrast, animate=False):
        self.snapshot = snapshot
        c = self.canvas
        if self.motion_job is not None:
            c.after_cancel(self.motion_job)
            self.motion_job = None
        c.delete("all")
        ink = "#ffffff" if contrast else "#edf2fb"
        dim = "#ffffff" if contrast else "#a9b7c8"
        bg = "#000000" if contrast else "#111b29"
        accent = "#ffff00" if contrast else ACCENTS[snapshot.state]
        c.configure(bg=bg)
        if self.index == 0:
            # Split Prism: two offset faceted blades and a narrow lit seam.
            c.create_polygon(28, 78, 78, 53, 67, 120, 38, 138, fill=accent)
            c.create_polygon(84, 48, 116, 77, 93, 137, 72, 123, fill="#52647b" if not contrast else ink)
            c.create_line(72, 74, 70, 116, fill=bg, width=5)
            c.create_rectangle(128, 58, 340, 142, fill="#1b2b3d" if not contrast else bg,
                               outline=accent, width=2)
            label_x, label_y, text_x, text_y = 144, 75, 144, 105
            c.create_line(20, 160, 340, 160, fill=accent, width=2)
        elif self.index == 1:
            # Folded Kite: one vertical asymmetric crystal with an inward cut.
            c.create_polygon(180, 24, 226, 94, 182, 148, 150, 108, 158, 50,
                             fill=accent)
            c.create_polygon(180, 24, 182, 148, 150, 108, fill="#52647b" if not contrast else bg)
            c.create_polygon(158, 50, 180, 83, 170, 105, fill=bg)
            c.create_rectangle(20, 160, 340, 308, fill="#1b2b3d" if not contrast else bg,
                               outline=accent, width=2)
            label_x, label_y, text_x, text_y = 36, 176, 36, 207
        else:
            # Cutline: three separated directional plates, no closed diamond.
            c.create_polygon(34, 58, 110, 58, 85, 82, 30, 82, fill=accent)
            c.create_polygon(28, 90, 82, 90, 61, 114, 20, 114, fill="#52647b" if not contrast else ink)
            c.create_polygon(76, 119, 117, 85, 117, 112, 91, 137, fill=accent)
            c.create_line(139, 59, 139, 142, fill=accent, width=3)
            c.create_rectangle(150, 58, 340, 142, fill="#1b2b3d" if not contrast else bg,
                               outline=dim, width=1)
            label_x, label_y, text_x, text_y = 164, 74, 164, 104
            c.create_rectangle(20, 160, 340, 171, fill=accent, outline="")
        c.create_text(label_x, label_y, anchor="nw", text=LABELS[snapshot.state],
                      fill=accent, font=("Segoe UI Semibold", 11))
        c.create_text(text_x, text_y, anchor="nw", text=DETAILS[snapshot.state],
                      fill=ink, width=180 if self.index != 1 else 280,
                      font=("Segoe UI", 10))
        if expanded:
            if self.index != 1:
                c.create_rectangle(20, 181, 340, 286, fill="#1b2b3d" if not contrast else bg,
                                   outline=dim, width=1)
            display = clipped_lines(snapshot.transcript or "No transcript available")
            c.create_text(34, 192 if self.index != 1 else 238, anchor="nw",
                          text=display, width=290, fill=ink, font=("Segoe UI", 11))
        else:
            c.create_text(22, 295, anchor="nw", text="COMPACT · expandable on activation",
                          fill=dim, font=("Segoe UI", 9))
        accessible_text = (f"{LABELS[snapshot.state]}. {DETAILS[snapshot.state]}. "
                           f"Transcript: {snapshot.transcript or 'none'}. ")
        if snapshot.outcome:
            accessible_text += f"Outcome: {snapshot.outcome.value}."
        self.accessible.configure(text=accessible_text)
        if animate and snapshot.state != DisplayState.IDLE:
            self._reveal(accent, 0)

    def _reveal(self, accent, step):
        self.canvas.delete("reveal")
        self.canvas.create_line(20, 314, (120, 230, 340)[step], 314,
                                fill=accent, width=2, tags="reveal")
        if step < 2:
            self.motion_job = self.canvas.after(45, self._reveal, accent, step + 1)
        else:
            self.motion_job = None


class Gallery:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ARIA Phase 8B · synthetic Shard design gallery")
        self.root.geometry("1210x680")
        self.root.minsize(1130, 620)
        self.root.configure(bg="#0b121e")
        self.state = tk.StringVar(value=DisplayState.IDLE.value)
        self.expanded = tk.BooleanVar(value=True)
        self.contrast = tk.BooleanVar(value=False)
        self.reduced_motion = tk.BooleanVar(value=False)
        self.long_text = tk.BooleanVar(value=False)
        self.snapshot = synthetic_snapshot(DisplayState.IDLE)
        self._previous_state = DisplayState.IDLE
        top = ttk.Frame(self.root, padding=16)
        top.pack(fill="x")
        ttk.Label(top, text="ARIA / Shard directions", font=("Segoe UI Semibold", 20)).pack(anchor="w")
        ttk.Label(top, text="Design study · all states and transcripts are synthetic · no command path",
                  font=("Segoe UI", 10)).pack(anchor="w")
        controls = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="State").pack(side="left")
        selector = ttk.Combobox(controls, textvariable=self.state, state="readonly",
                                values=[state.value for state in DisplayState], width=16)
        selector.pack(side="left", padx=6)
        selector.bind("<<ComboboxSelected>>", lambda _event: self.update())
        for label, variable in (("Expanded", self.expanded), ("Long transcript", self.long_text),
                                ("High contrast", self.contrast),
                                ("Reduced motion", self.reduced_motion)):
            ttk.Checkbutton(controls, text=label, variable=variable,
                            command=self.update).pack(side="left", padx=8)
        ttk.Button(controls, text="Next state", command=self.next_state).pack(side="right")
        row = ttk.Frame(self.root, padding=8)
        row.pack(fill="both", expand=True)
        definitions = [
            ("01 / Split Prism", "Horizontal blade pair · left anchored status rail"),
            ("02 / Folded Kite", "Vertical asymmetric mark · centered transcript card"),
            ("03 / Cutline", "Open directional plates · segmented status strip"),
        ]
        self.cards = []
        for index, (name, description) in enumerate(definitions):
            card = ConceptCard(row, index, name, description, self.full_transcript)
            card.pack(side="left", fill="both", expand=True, padx=5)
            self.cards.append(card)
        self.root.bind("<Right>", lambda _event: self.next_state())
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.update()

    def next_state(self):
        states = list(DisplayState)
        self.state.set(states[(states.index(DisplayState(self.state.get())) + 1) % len(states)].value)
        self.update()

    def update(self):
        self.snapshot = synthetic_snapshot(DisplayState(self.state.get()), self.long_text.get())
        changed = self.snapshot.state != self._previous_state
        for card in self.cards:
            card.render(self.snapshot, self.expanded.get(), self.contrast.get(),
                        animate=changed and not self.reduced_motion.get())
        self._previous_state = self.snapshot.state

    def full_transcript(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Synthetic full transcript")
        dialog.geometry("520x260")
        ttk.Label(dialog, text="Synthetic transcript · display only", padding=12).pack(anchor="w")
        box = tk.Text(dialog, wrap="word", height=7, padx=12, pady=12)
        box.insert("1.0", self.snapshot.transcript or "No transcript available")
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=12)
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=8)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        box.focus_set()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Gallery().run()
