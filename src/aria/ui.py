"""Small Tk status overlay. Tk calls run only on the UI thread."""
import ctypes
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from aria.activation import ActivationController, State
from aria.hotkey import GlobalHotkey
from aria.permissions import PermissionEngine


class ConfirmationDialog:
    def __init__(self, root, prompt, clock=time.monotonic):
        self.prompt = prompt
        self.clock = clock
        self.window = tk.Toplevel(root)
        self.window.title("ARIA confirmation")
        self.window.attributes("-topmost", True)
        self.window.resizable(False, False)
        ttk.Label(self.window, text=prompt.pending.description, wraplength=520, padding=20).pack()
        self.countdown = ttk.Label(self.window, padding=(20, 0))
        self.countdown.pack()
        bar = ttk.Frame(self.window, padding=16)
        bar.pack(fill="x")
        self.cancel_button = ttk.Button(bar, text="Cancel", command=lambda: self.finish("cancelled"))
        self.cancel_button.pack(side="left")
        self.confirm_button = ttk.Button(bar, text="Confirm", command=lambda: self.finish("confirmed"))
        self.confirm_button.pack(side="right")
        self.window.protocol("WM_DELETE_WINDOW", lambda: self.finish("cancelled"))
        self.window.bind("<Escape>", lambda _event: self.finish("cancelled"))
        self.cancel_button.focus_set()
        self.window.update_idletasks()
        prompt.timeline.mark("confirmation_start")
        self.timer = None
        self._tick()

    def _tick(self):
        if self.prompt.done.is_set():
            self.destroy()
            return
        left = self.prompt.pending.expires_at-self.clock()
        if left <= 0:
            self.finish("timed_out")
            return
        self.countdown.configure(text=f"Expires in {left:.0f} seconds")
        self.timer = self.window.after(100, self._tick)

    def finish(self, answer):
        if self.clock() >= self.prompt.pending.expires_at:
            answer = "timed_out"
        self.prompt.respond(answer)
        self.destroy()

    def destroy(self):
        if self.timer:
            self.window.after_cancel(self.timer)
            self.timer = None
        if self.window.winfo_exists():
            self.window.destroy()


class DesktopApp:
    def __init__(self, model="base", timeout=30, confirm_low=False, voice_factory=None):
        from aria.engine import Engine
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("ARIA")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.events = queue.Queue()
        self.controller = None
        self.hotkey = None
        self.dialog = None
        self.closed = False
        self.started = time.perf_counter()
        self.engine = Engine(permissions=PermissionEngine(timeout, confirm_low))
        self.label = ttk.Label(self.root, text="ARIA — Loading local speech model…", padding=14, wraplength=350)
        self.label.pack()
        ttk.Button(self.root, text="Quit", command=self.close).pack(pady=(0, 8))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.update_idletasks()
        self._show_without_focus()
        self.root.after(10, self._drain)

        def load():
            try:
                from aria.voice import LocalASR, VoiceController
                voice = voice_factory(self.engine) if voice_factory else VoiceController(self.engine, asr=LocalASR(model))
                self.events.put(("loaded", voice))
            except Exception as exc:
                import logging
                logging.getLogger("aria").exception("speech_model_load_failed")
                self.events.put(("load_error", f"Local model unavailable: {exc}. Cache the model before starting ARIA."))
        threading.Thread(target=load, name="aria-model-load", daemon=True).start()

    def _show_without_focus(self):
        u32 = ctypes.windll.user32
        u32.GetParent.argtypes = [ctypes.c_void_p]
        u32.GetParent.restype = ctypes.c_void_p
        hwnd = u32.GetParent(self.root.winfo_id())
        get_style = u32.GetWindowLongPtrW
        set_style = u32.SetWindowLongPtrW
        get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        set_style.restype = ctypes.c_ssize_t
        set_style(hwnd, -20, get_style(hwnd, -20) | 0x08000000 | 0x80)
        self.root.geometry(f"+{max(0,self.root.winfo_screenwidth()-400)}+{max(0,self.root.winfo_screenheight()-180)}")
        self.root.deiconify()

    def _drain(self):
        if self.closed:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "loaded":
                    self.controller = ActivationController(self.engine, payload, lambda k,p: self.events.put((k,p)))
                    self.hotkey = GlobalHotkey(self.controller.activate)
                    try:
                        self.hotkey.start()
                        self.label.configure(text="ARIA — Idle\nCtrl + Space to speak")
                        import logging
                        logging.getLogger("aria").info("desktop_startup_ms=%.3f", (time.perf_counter()-self.started)*1000)
                    except OSError as exc:
                        self.label.configure(text=f"ARIA — Error\n{exc}")
                elif kind == "load_error":
                    self.label.configure(text=f"ARIA — Error\n{payload}")
                elif kind == "state":
                    state, message, line = payload
                    self.label.configure(text=f"ARIA — {state.value.replace('_', ' ').title()}\n{message or ('Ctrl + Space to speak' if state == State.IDLE else '')}")
                    if state == State.LISTENING and line:
                        self.root.update_idletasks()
                        line.mark("listening_start")
                elif kind == "confirmation":
                    if not payload.done.is_set():
                        self.dialog = ConfirmationDialog(self.root, payload, self.engine.permissions.clock)
                elif kind == "dismiss":
                    if self.dialog and self.dialog.prompt is payload:
                        self.dialog.destroy()
                        self.dialog = None
                elif kind == "complete":
                    self.root.after(1000, self.controller.ready)
        except queue.Empty:
            pass
        self.root.after(10, self._drain)

    def close(self):
        self.closed = True
        if self.dialog:
            self.dialog.finish("cancelled")
        if self.controller:
            self.controller.close()
        if self.hotkey:
            self.hotkey.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
