from __future__ import annotations

import argparse, atexit, logging
from pathlib import Path

from aria.engine import ConfirmationRequired, Engine
from aria.parser import ParseError

HELP = "Commands: open <app|website>, search the web for <query>, search YouTube for <query>, play <video>, type <text> in <field>, click <element>, download <link>, window/file/volume commands, quit"


def main() -> int:
    options=argparse.ArgumentParser()
    mode=options.add_mutually_exclusive_group()
    mode.add_argument("--voice",action="store_true")
    mode.add_argument("--desktop",action="store_true")
    options.add_argument("--model",default="base")
    options.add_argument("--confirmation-timeout",type=float,default=30)
    options.add_argument("--confirm-low",action="store_true")
    options.add_argument("--browser-headless", action="store_true")
    options.add_argument("--browser-startup-timeout", type=int, default=15000, metavar="MS")
    options.add_argument("--browser-navigation-timeout", type=int, default=20000, metavar="MS")
    options.add_argument("--browser-element-timeout", type=int, default=8000, metavar="MS")
    options.add_argument("--browser-download-timeout", type=int, default=20000, metavar="MS")
    args=options.parse_args()
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(filename="logs/aria.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from aria.permissions import PermissionEngine
    from aria.browser import BrowserConfig, BrowserManager
    browser_config = BrowserConfig(
        headless=args.browser_headless,
        startup_timeout_ms=args.browser_startup_timeout,
        navigation_timeout_ms=args.browser_navigation_timeout,
        element_timeout_ms=args.browser_element_timeout,
        download_timeout_ms=args.browser_download_timeout,
    )
    browser_factory = lambda: BrowserManager(browser_config)
    policy = PermissionEngine(args.confirmation_timeout, args.confirm_low)
    if args.desktop:
        from aria.ui import DesktopApp
        DesktopApp(args.model, args.confirmation_timeout, args.confirm_low, browser_factory=browser_factory).run()
        return 0
    engine = Engine(permissions=policy, browser_factory=browser_factory)
    atexit.register(engine.close)
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
