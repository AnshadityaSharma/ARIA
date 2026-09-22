from __future__ import annotations

import argparse, logging
from pathlib import Path

from aria.engine import ConfirmationRequired, Engine
from aria.parser import ParseError

HELP = "Commands: open <app>, make it one-fifth of the screen, make it smaller/bigger, move it top right/left/right/up/down, minimize/maximize/restore, create folder <name> on desktop, take screenshot, set volume 50%, mute/unmute, quit"


def main() -> int:
    options=argparse.ArgumentParser(); options.add_argument("--voice",action="store_true"); options.add_argument("--model",default="base"); args=options.parse_args()
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(filename="logs/aria.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = Engine()
    if args.voice:
        from aria.voice import LocalASR, VoiceController, VoiceError
        voice=VoiceController(engine,asr=LocalASR(args.model)); print("ARIA local voice mode. Press Enter to speak; Ctrl+C to quit.")
        while True:
            try:
                input(); transcript,result,line=voice.run_once(); print(f"{transcript.text} [{transcript.confidence:.0%}] -> {result.message}"); print(line.milliseconds())
            except VoiceError as exc: print(f"Voice: {exc}")
            except (EOFError,KeyboardInterrupt): print(); return 0
            except (ParseError,LookupError,ValueError,OSError,ConfirmationRequired) as exc: print(f"Error: {exc}")
    print("ARIA deterministic desktop core. Type 'help' or 'quit'.")
    while True:
        try: text = input("aria> ").strip()
        except (EOFError, KeyboardInterrupt): print(); return 0
        if text in {"quit", "exit"}: return 0
        if text == "help": print(HELP); continue
        try: print(engine.run_text(text).message)
        except (ParseError, LookupError, ValueError, OSError, ConfirmationRequired) as exc: print(f"Error: {exc}")
