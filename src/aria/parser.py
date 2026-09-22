from __future__ import annotations

import re
from pathlib import Path

from aria.core import Action, ActionType


class ParseError(ValueError):
    pass


def parse(text: str) -> Action:
    # Preserve path punctuation and case before normalizing command grammar.
    if m := re.fullmatch(r'delete(?: file)?\s+(.+)', text.strip(), re.IGNORECASE):
        return Action(ActionType.DELETE_PATH, m.group(1).strip().strip('"')).validate()
    if m := re.fullmatch(r'(move|copy|rename) file\s+(.+?)\s+to\s+(.+)', text.strip(), re.IGNORECASE):
        kind = {"move": ActionType.MOVE_PATH, "copy": ActionType.COPY_PATH, "rename": ActionType.RENAME_PATH}[m.group(1).lower()]
        return Action(kind, m.group(2).strip().strip('"'), {"destination": m.group(3).strip().strip('"')}).validate()
    raw = " ".join(text.strip().lower().split())
    if raw in {"shutdown", "shut down", "shut down computer"}:
        return Action(ActionType.SHUTDOWN)
    if not raw:
        raise ParseError("Command is empty")
    if m := re.fullmatch(r"open (?:application |app )?(.+)", raw):
        target = m.group(1)
        if target in {"desktop", "documents", "downloads", "videos", "pictures"} or "\\" in target or ":/" in target:
            return Action(ActionType.OPEN_PATH, target)
        return Action(ActionType.OPEN_APPLICATION, target).validate()
    if m := re.fullmatch(r"(?:focus|switch to) (.+)", raw):
        return Action(ActionType.FOCUS_WINDOW, m.group(1))
    for verb, kind in (("minimize", ActionType.MINIMIZE_WINDOW), ("maximize", ActionType.MAXIMIZE_WINDOW), ("restore", ActionType.RESTORE_WINDOW)):
        if m := re.fullmatch(fr"{verb}(?: (.+))?", raw):
            return Action(kind, m.group(1) or "tracked")
    ref = r"(it|that|this window)"
    if m := re.fullmatch(fr"make {ref} (?:(\d+)% |a little |slightly )?(smaller|bigger)", raw):
        amount = int(m.group(2) or 10) / 100
        return Action(ActionType.RESIZE_WINDOW, "foreground" if m.group(1) == "this window" else "tracked", {"scale": 1-amount if m.group(3) == "smaller" else 1+amount}).validate()
    if m := re.fullmatch(fr"make {ref} (?:one[- ]fifth|20%)(?: of the screen)?", raw):
        return Action(ActionType.RESIZE_WINDOW, "foreground" if m.group(1) == "this window" else "tracked", {"screen_ratio": .2}).validate()
    if m := re.fullmatch(fr"make {ref} half (?:the |its )?size", raw):
        return Action(ActionType.RESIZE_WINDOW, "foreground" if m.group(1) == "this window" else "tracked", {"scale": .5}).validate()
    if m := re.fullmatch(r"resize (.+?) (\d+)%", raw):
        return Action(ActionType.RESIZE_WINDOW, m.group(1), {"screen_ratio": int(m.group(2)) / 100}).validate()
    if m := re.fullmatch(fr"move {ref}(?: (\d+) pixels?)?(?: slightly)?(?: to the)? (top right|top left|bottom right|bottom left|top|bottom|center|right|left|up|down)", raw):
        params = {"position": m.group(3).replace(" ", "_")}
        if m.group(2): params["pixels"] = int(m.group(2))
        return Action(ActionType.MOVE_WINDOW, "foreground" if m.group(1) == "this window" else "tracked", params)
    if m := re.fullmatch(r"move (.+?)(?: to)? (top right|top left|bottom right|bottom left|center)", raw):
        return Action(ActionType.MOVE_WINDOW, m.group(1), {"position": m.group(2).replace(" ", "_")})
    if m := re.fullmatch(r"create folder (?:called )?(.+?)(?: (?:in|on) (desktop|documents|downloads|videos|pictures))?", raw):
        return Action(ActionType.CREATE_FOLDER, m.group(2) or "desktop", {"name": m.group(1)})
    if raw in {"take screenshot", "take a screenshot"}:
        return Action(ActionType.TAKE_SCREENSHOT)
    if m := re.fullmatch(r"set volume (?:to )?(\d+)%?", raw):
        return Action(ActionType.SET_VOLUME, params={"level": int(m.group(1))})
    if m := re.fullmatch(r"(?:increase|decrease|raise|lower) volume(?: by)? (\d+)%?", raw):
        sign = -1 if raw.startswith(("decrease", "lower")) else 1
        return Action(ActionType.CHANGE_VOLUME, params={"delta": sign * int(m.group(1))})
    if raw in {"mute", "mute volume"}: return Action(ActionType.MUTE)
    if raw in {"unmute", "unmute volume"}: return Action(ActionType.UNMUTE)
    raise ParseError(f"Unsupported or ambiguous command: {text!r}")
