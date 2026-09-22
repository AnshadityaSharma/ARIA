from __future__ import annotations

import logging
from pathlib import Path

from aria.engine import ConfirmationRequired, Engine
from aria.parser import ParseError

HELP = "Commands: open <app>, make it one-fifth of the screen, make it smaller/bigger, move it top right/left/right/up/down, minimize/maximize/restore, create folder <name> on desktop, take screenshot, set volume 50%, mute/unmute, quit"


def main() -> int:
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(filename="logs/aria.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = Engine(); print("ARIA deterministic desktop core. Type 'help' or 'quit'.")
    while True:
        try: text = input("aria> ").strip()
        except (EOFError, KeyboardInterrupt): print(); return 0
        if text in {"quit", "exit"}: return 0
        if text == "help": print(HELP); continue
        try: print(engine.run_text(text).message)
        except (ParseError, LookupError, ValueError, OSError, ConfirmationRequired) as exc: print(f"Error: {exc}")

