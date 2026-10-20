"""Native Tk/Pillow Seam. Independent from DesktopApp and all command paths."""
from collections import deque
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
import threading
import time
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from aria.shard_presentation import DisplayState as S
from aria.seam_presentation import (ATTENTION, ICONS, LABELS, SeamAdapter,
                                     SeamMotion, placement)
from aria.seam_windows import WindowsSurface

KEY = "#ff00ff"


@lru_cache(maxsize=32)
def font(size):
    for path in (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def fit_text(text, face, width):
    text = " ".join(text.split())
    if face.getlength(text) <= width:
        return text
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if face.getlength(text[:mid] + "…") <= width:
            low = mid
        else:
            high = mid - 1
    return text[:low] + "…"


def seam_image(frame, motion, scale=1., caption=True, contrast=False):
    width = max(1, round(motion["width"]*scale))
    image = _seam_base(frame.compact_state, frame.snapshot.transcript, frame.fault,
                       width, scale, caption, contrast).copy()
    draw = ImageDraw.Draw(image)
    cx = width/2+motion["offset"]*scale
    beam = motion["beam"]*scale/2
    draw.line((cx-beam, 2*scale, cx+beam, 2*scale), fill="#f0fff9", width=max(1, round(2*scale)))
    gap = 8 if frame.compact_state == S.FAILED else 3 if frame.compact_state == S.UNVERIFIED else 0
    if gap:
        draw.rectangle((width/2-gap*scale/2, 0, width/2+gap*scale/2, 4*scale), fill="#000000" if contrast else "#172529")
    return image


@lru_cache(maxsize=24)
def _seam_base(state, transcript, fault, w, scale, caption, contrast):
    """Antialiased, bounded, self-contained material; no wallpaper readback/blur."""
    h = max(1, round((23 if state == S.IDLE else 26) * scale))
    ss = 3
    image = Image.new("RGBA", (w*ss, h*ss))
    draw = ImageDraw.Draw(image)
    fill = "#000000" if contrast else "#172529"
    draw.rounded_rectangle((0, -12*ss, w*ss-1, h*ss-1), radius=9*scale*ss, fill=fill)
    color = "#ffffff" if contrast else ("#e3b4a8" if state == S.FAILED else
                                        "#dfc8a1" if state in {S.CONFIRMATION, S.UNVERIFIED} else "#b8e6d9")
    margin = round(11*scale*ss)
    draw.line((margin, 2*ss, w*ss-margin, 2*ss), fill=color, width=max(1, round(scale*ss)))
    if state == S.CONFIRMATION:
        for x in (margin, w*ss-margin):
            draw.line((x, 0, x, 5*scale*ss), fill=color, width=max(1, round(scale*ss)))
    idle = state == S.IDLE
    text = "aria" if idle else transcript or LABELS[state]
    if fault:
        text = "Presentation unavailable"
    face = font(max(8, round((9 if idle else 10)*scale*ss)))
    if caption or idle:
        text = fit_text(text, face, max(1, (w-30*scale)*ss))
        draw.text((w*ss/2, 17*scale*ss), text, fill="#ffffff" if contrast else "#b7cdc3", font=face, anchor="mm")
    icon = "!" if fault else ICONS.get(state, "")
    if icon:
        draw.text(((w-7*scale)*ss, 17*scale*ss), icon, fill=color, font=face, anchor="mm")
    image = image.resize((w, h), Image.Resampling.LANCZOS)
    # Tk's color-key windows have binary outer transparency. Composite edge RGB
    # against the material (not magenta), avoiding bright color-key fringes.
    rgb = Image.new("RGB", image.size, fill)
    rgb.paste(image, mask=image.getchannel("A"))
    mask = image.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    keyed = Image.new("RGB", image.size, KEY)
    keyed.paste(rgb, mask=mask)
    return keyed


class SeamWindow:
    def __init__(self, root, adapter=None, backend=None, clock=time.perf_counter):
        self.root, self.clock = root, clock
        self.adapter = adapter if adapter is not None else SeamAdapter(clock)
        self.backend = backend if backend is not None else WindowsSurface()
        self.thread = threading.get_ident()
        self.area = self.backend.work_area()
        self.high_contrast, self.reduced_motion = self.backend.preferences()
        self.preference_override = None
        self.panel_interactive = False
        self.caption = True
        self.visible = True
        self.closed = False
        self.fault = None
        self.frame = None
        self.motion = SeamMotion()
        self.jobs = set()
        self.animation_job = None
        self.last_animation = clock()
        self.next_monitor_check = clock() + 1
        self.paint_ms = deque(maxlen=512)
        self.event_to_paint_ms = deque(maxlen=512)
        self._painted_event = None
        self.frame_intervals_ms = deque(maxlen=512)
        self.paint_count = 0
        self.decision_intents = deque(maxlen=8)
        self.image = None
        self._panel_key = None
        self._compact_geometry = None
        self._panel_geometry = None
        self.compact = tk.Toplevel(root)
        self.compact.withdraw()
        self.compact.title("ARIA Seam status")
        self.compact.overrideredirect(True)
        self.compact.attributes("-topmost", True)
        self.compact.attributes("-transparentcolor", KEY)
        self.canvas = tk.Canvas(self.compact, bg=KEY, highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True)
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.panel = tk.Toplevel(root)
        self.panel.withdraw()
        self.panel.title("ARIA transcript and status")
        self.panel.overrideredirect(True)
        self.panel.attributes("-topmost", True)
        self.body = tk.Frame(self.panel, bg="#1d292c", bd=1, relief="flat")
        self.body.pack(fill="both", expand=True)
        self.status = tk.Label(self.body, text="ARIA · Ready", bg="#1d292c", fg="#a7bfb4", anchor="w")
        self.status.pack(fill="x", padx=13, pady=(10, 6))
        text_area = tk.Frame(self.body, bg="#1d292c")
        text_area.pack(fill="both", expand=True, padx=13)
        self.text = tk.Text(text_area, height=1, wrap="char", bg="#1d292c", fg="#e1ece6", bd=0,
                            highlightthickness=1, highlightbackground="#1d292c", highlightcolor="#a9cfbc",
                            insertbackground="#e1ece6", takefocus=True, exportselection=False)
        self.scroll = tk.Scrollbar(text_area, command=self.text.yview, width=10)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.message = tk.Label(self.body, text="", justify="left", anchor="w", bg="#1d292c", fg="#aec0b7")
        self.message.pack(fill="x", padx=13, pady=6)
        self.actions = tk.Frame(self.body, bg="#1d292c")
        self.actions.pack(fill="x", padx=10, pady=(0, 8))
        button_style = dict(font=("Segoe UI", -10), padx=7, pady=4, bd=0,
                            bg="#293a3b", fg="#d7e5df", activebackground="#3a4e4c",
                            activeforeground="#ffffff", highlightthickness=1,
                            highlightbackground="#405652", highlightcolor="#b8e6d9")
        self.confirm = tk.Button(self.actions, text="Confirm demo", command=lambda: self.intent("confirm"), **button_style)
        self.cancel = tk.Button(self.actions, text="Cancel demo", command=lambda: self.intent("cancel"), **button_style)
        self.close_button = tk.Button(self.actions, text="Close details", command=self.collapse, **button_style)
        self.close_button.pack(side="right")
        self.canvas.bind("<Button-1>", lambda _: self.expand(interactive=True))
        self.canvas.bind("<Return>", lambda _: self.expand(interactive=True))
        self.canvas.bind("<space>", lambda _: self.expand(interactive=True))
        self.canvas.bind("<Down>", lambda _: self.expand(interactive=True))
        self.compact.bind("<Enter>", lambda _: self._hover(True))
        self.compact.bind("<Leave>", lambda _: self._later(160, self._check_hover))
        self.panel.bind("<Enter>", lambda _: self._hover(True))
        self.panel.bind("<Leave>", lambda _: self._later(160, self._check_hover))
        self.panel.bind("<Escape>", lambda _: self.collapse())
        self.compact.protocol("WM_DELETE_WINDOW", self.close)
        self.panel.protocol("WM_DELETE_WINDOW", self.collapse)
        self._pump()

    def _later(self, ms, fn):
        if self.closed:
            return None
        def call():
            self.jobs.discard(job)
            if not self.closed:
                fn()
        job = self.root.after(ms, call)
        self.jobs.add(job)
        return job

    def _hover(self, value):
        self.adapter.hover = value

    def _check_hover(self):
        x, y = self.root.winfo_pointerxy()
        inside = False
        for window in (self.compact, self.panel):
            if window.winfo_viewable():
                inside |= (window.winfo_rootx() <= x < window.winfo_rootx()+window.winfo_width() and
                           window.winfo_rooty() <= y < window.winfo_rooty()+window.winfo_height())
        self.adapter.hover = inside

    def _pump(self):
        if self.closed:
            return
        try:
            now = self.clock()
            if now >= self.next_monitor_check:
                self.next_monitor_check = now + 1
                area = self.backend.work_area(self.backend.hwnd(self.compact))
                if area != self.area:
                    self.area = area
                    self.adapter.last_frame = None
                high, reduced = self.preference_override or self.backend.preferences()
                if high != self.high_contrast or reduced != self.reduced_motion:
                    self.high_contrast, self.reduced_motion = high, reduced
                    self.adapter.last_frame = None
            frame = self.adapter.advance()
            if frame is not None:
                self.frame = frame
                self.motion.retarget(frame, self.caption)
                self._paint()
                self._start_animation()
        except Exception:
            self._render_failed()
        self._later(20 if self.visible else 100, self._pump)

    def _paint(self):
        if not self.visible or not self.frame:
            return
        start = self.clock()
        image = seam_image(self.frame, self.motion.value, self.area.scale, self.caption, self.high_contrast)
        self.image = ImageTk.PhotoImage(image, master=self.compact)
        self.canvas.itemconfigure(self.image_item, image=self.image)
        x, y, w, h = placement(self.area, self.motion.value["width"], 23 if self.frame.compact_state == S.IDLE else 26)
        geometry = f"{w}x{h}{x:+d}{y:+d}"
        if geometry != self._compact_geometry:
            self._compact_geometry = geometry
            self.compact.geometry(geometry)
            self.compact.update_idletasks()
            self.backend.style(self.compact)
        if not self.compact.winfo_viewable():
            self.backend.show(self.compact)
        self._panel()
        self.paint_count += 1
        self.paint_ms.append((self.clock()-start)*1000)
        key = (self.frame.snapshot.session_id, self.frame.snapshot.sequence)
        if (key != self._painted_event and self.adapter.latest_received_at is not None
                and self.frame.compact_state == self.frame.snapshot.state):
            self._painted_event = key
            self.event_to_paint_ms.append((self.clock()-self.adapter.latest_received_at)*1000)

    def _panel(self):
        frame = self.frame
        if not frame.expanded:
            self.panel.withdraw()
            return
        key = (frame.snapshot, frame.speaking, frame.fault, self.high_contrast, self.area)
        if key != self._panel_key:
            self._panel_key = key
            s = frame.snapshot.state
            bg, fg = ("#000000", "#ffffff") if self.high_contrast else ("#1d292c", "#e1ece6")
            for widget in (self.body, self.status, self.text, self.message, self.actions):
                widget.configure(bg=bg)
            self.status.configure(text="ARIA · "+("Speaking / "+LABELS[s] if frame.speaking else LABELS[s]),
                                  fg=fg, font=("Segoe UI", -round(10*self.area.scale)))
            self.text.configure(state="normal", fg=fg, font=("Segoe UI", -round(12*self.area.scale)))
            self.text.delete("1.0", "end")
            self.text.insert("1.0", frame.snapshot.transcript or "No transcript available.")
            self.text.configure(state="disabled")
            self.message.configure(text=frame.fault or {
                S.CONFIRMATION: "Review this request. Demo controls do not run actions.",
                S.FAILED: "The action could not be completed.",
                S.UNVERIFIED: "The action ran, but its result could not be verified.",
                S.CANCELLED: "Cancelled.",
            }.get(s, ""), fg=fg, wraplength=round(250*self.area.scale), font=("Segoe UI", -round(10*self.area.scale)))
            for button in (self.confirm, self.cancel):
                button.pack_forget()
            for button in (self.confirm, self.cancel, self.close_button):
                button.configure(font=("Segoe UI", -round(10*self.area.scale)))
                if self.high_contrast:
                    button.configure(bg="#000000", fg="#ffffff", highlightbackground="#ffffff")
                else:
                    button.configure(bg="#293a3b", fg="#d7e5df", highlightbackground="#405652")
            if s == S.CONFIRMATION:
                self.cancel.pack(side="left", pady=2)
                self.confirm.pack(side="left", pady=2)
        long = len(frame.snapshot.transcript) > 130 or frame.snapshot.transcript.count("\n") > 2
        height = 208 if frame.snapshot.state == S.CONFIRMATION else 178 if long else 122
        x, y, w, h = placement(self.area, 280, height, 32)
        geometry = f"{w}x{h}{x:+d}{y:+d}"
        if geometry != self._panel_geometry:
            self._panel_geometry = geometry
            self.panel.geometry(geometry)
            self.panel.update_idletasks()
            self.backend.style(self.panel, self.panel_interactive)
        if not self.panel.winfo_viewable():
            self.backend.show(self.panel)

    def _start_animation(self):
        if self.animation_job or self.closed or not self.visible:
            return
        self.last_animation = self.clock()
        self.animation_job = self._later(16, self._animate)

    def _animate(self):
        self.animation_job = None
        if not self.visible or self.adapter.hidden:
            return
        try:
            self._animate_frame()
        except Exception:
            self._render_failed()

    def _render_failed(self):
        self.fault = "Seam renderer unavailable"
        self.adapter.hidden = True
        if self.animation_job:
            self.root.after_cancel(self.animation_job)
            self.jobs.discard(self.animation_job)
            self.animation_job = None
        for window in (self.compact, self.panel):
            try:
                window.withdraw()
            except tk.TclError:
                pass

    def _animate_frame(self):
        now = self.clock()
        interval = now-self.last_animation
        self.last_animation = now
        self.frame_intervals_ms.append(interval*1000)
        if self.motion.step(interval, self.reduced_motion):
            self._paint()
            self.animation_job = self._later(16, self._animate)
        else:
            self._paint()

    def expand(self, interactive=False):
        self.panel_interactive = bool(interactive)
        self.adapter.pinned = True
        self.adapter.dismissed = False
        frame = self.adapter.advance()
        if frame:
            self.frame = frame
        if self.frame:
            self._panel()
            if interactive:
                self.backend.show(self.panel, interactive=True)
                self.text.focus_force()  # only after the user's explicit inspection action

    def collapse(self):
        self.panel_interactive = False
        self.adapter.dismiss()
        self.panel.withdraw()

    def intent(self, decision):
        # Typed session identity only; deliberately no command/authorization callback.
        if self.frame and self.frame.snapshot.state == S.CONFIRMATION:
            self.decision_intents.append((self.frame.snapshot.session_id, self.frame.snapshot.sequence, decision))
            self.message.configure(text="Demo choice recorded.")

    def set_visible(self, visible):
        self.visible = bool(visible)
        self.adapter.hidden = not self.visible
        self.adapter.last_frame = None
        if not visible:
            self.compact.withdraw()
            self.panel.withdraw()
            if self.animation_job:
                self.root.after_cancel(self.animation_job)
                self.jobs.discard(self.animation_job)
                self.animation_job = None

    def recover(self):
        if self.closed:
            return False
        self.fault = None
        self.set_visible(True)
        self.area = self.backend.work_area()
        return True

    def close(self):
        if self.closed:
            return
        self.closed = True
        for job in tuple(self.jobs):
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self.jobs.clear()
        self.adapter.close()
        _seam_base.cache_clear()  # cached captions are memory only; release on shutdown
        self.frame = None
        self.image = None
        for window in (self.compact, self.panel):
            try:
                window.destroy()
            except tk.TclError:
                pass
