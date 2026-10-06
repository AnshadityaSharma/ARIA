
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from aria.core import Action, ActionType


class ParseError(ValueError): pass
class ClarificationRequired(ParseError, LookupError): pass
class UnsupportedCommand(ParseError): pass
class MalformedCommand(ParseError): pass


@dataclass(frozen=True, slots=True)
class Token:
    control: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class NormalizedCommand:
    source: str
    surface: str
    control: str
    tokens: tuple[Token, ...]


POLITE_PREFIX = re.compile(
    r"^(?:(?:please|kindly)\s+|(?:(?:could|can|would|will)\s+you)\s+)+", re.I)
POLITE_SUFFIX = r"(?:\s+(?:please|for me|once))?"


def normalize_command(text: str) -> NormalizedCommand:
    if not isinstance(text, str) or not text.strip() or len(text) > 1024:
        raise MalformedCommand("Provide one short, explicit computer command.")
    if any(ord(character) < 32 for character in text):
        raise MalformedCommand("Control characters are not accepted in commands.")
    source = unicodedata.normalize("NFKC", text).strip()
    surface = source
    if not re.search(r'[\\/:"?]', surface.rstrip(".!?")):
        surface = surface.rstrip(".!?")
    surface = POLITE_PREFIX.sub("", surface).strip()
    tokens = tuple(Token(match.group(0).casefold(), match.start(), match.end())
                   for match in re.finditer(r"\S+", surface))
    return NormalizedCommand(source, surface, " ".join(t.control for t in tokens), tokens)


NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100,
}
ONES = "one|two|three|four|five|six|seven|eight|nine"
NUMBER = rf"(?:\d+|zero|{ONES}|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|(?:twenty|thirty)(?:[- ](?:{ONES}))?|forty|fifty|sixty|seventy|eighty|ninety|hundred)"


def _number(value: str) -> int:
    value = value.casefold().replace("-", " ").strip()
    if value.isdigit(): return int(value)
    parts = value.split()
    if len(parts) == 1 and parts[0] in NUMBER_WORDS: return NUMBER_WORDS[parts[0]]
    if len(parts) == 2:
        first, second = NUMBER_WORDS.get(parts[0]), NUMBER_WORDS.get(parts[1])
        if first in range(20, 100, 10) and second in range(1, 10): return first + second
    raise ParseError(f"Unsupported number: {value!r}")


DIRECTIONS = {
    "upper right": "top_right", "top right": "top_right",
    "upper left": "top_left", "top left": "top_left",
    "lower right": "bottom_right", "bottom right": "bottom_right",
    "lower left": "bottom_left", "bottom left": "bottom_left",
    "top": "top", "bottom": "bottom", "center": "center",
    "right": "right", "left": "left", "up": "up", "down": "down",
}
DIRECTION = "|".join(sorted((re.escape(x) for x in DIRECTIONS), key=len, reverse=True))
REFERENCE = r"it|that(?: window)?|this window|the window|(?:the )?current window|(?:the )?active window"


def _reference(value: str) -> str:
    key = " ".join(value.casefold().split())
    return "foreground" if key in {"this window", "the window", "current window", "the current window", "active window", "the active window"} else "tracked"


def _trim_target(value: str) -> str:
    value = value.strip().strip('"')
    value = re.sub(r"^the\s+", "", value, flags=re.I)
    return re.sub(r"\s+(?:please|for me|once)$", "", value, flags=re.I).strip()


def _known_folder(value: str) -> str | None:
    key = re.sub(r"\s+folder$", "", value.casefold().strip())
    return {"desktop": "desktop", "document": "documents", "documents": "documents",
            "download": "downloads", "downloads": "downloads", "picture": "pictures",
            "pictures": "pictures", "video": "videos", "videos": "videos"}.get(key)


def _literal_command(control: str) -> bool:
    return bool(re.match(r"^(?:search (?:the )?web for|search youtube for|type |play |download )", control))


def _control_without_quoted_literals(surface: str) -> str:
    masked = re.sub(r'"[^"\r\n]*"', ' "literal" ', surface)
    return " ".join(masked.casefold().split())


def guard(command: NormalizedCommand) -> None:
    control = (command.control if '"' not in command.surface
               else _control_without_quoted_literals(command.surface))
    if "<|" in command.source:
        raise MalformedCommand("Model control delimiters are not accepted in commands.")
    if _literal_command(control): return
    if re.search(r"\b(?:do not|don't|dont|never|no need to)\b", control):
        raise UnsupportedCommand("The command is negated; nothing was proposed.")
    if re.search(r"\b(?:and|then)\s+(?:then\s+)?(?:open|launch|start|look|search|move|put|place|make|resize|delete|remove|run|click|type|play|maximize|minimize|restore)\b", control):
        raise ClarificationRequired("Please give one action at a time; split that request into separate commands.")
    if re.search(r"\b(?:delete|remove|erase)(?:\s+(?:file|folder))?\s+(?:it|that|everything|all)\b", control):
        raise UnsupportedCommand("Specify exactly one file or folder to delete.")
    if re.fullmatch(r"open\s+(?:that|it|this|something)", control):
        raise ClarificationRequired("Name the application, file, or website to open.")
    if re.match(r"^(?:do something|(?:move|shift) (?:the )?(?:thing|object))\b", control):
        raise ClarificationRequired("Specify the action, target, and required direction or size.")
    if re.match(r"^(?:send\s+(?:an?\s+)?(?:email|message)|buy\b|pay\b|run\s+(?:this\s+)?(?:command|code|script)|execute\s+(?:code|script))", control):
        raise UnsupportedCommand("That request is outside the supported computer capabilities.")


def _literal(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r'"[^"\r\n]+"[.!?]', value): value = value[:-1]
    if value.startswith('"') or value.endswith('"'):
        if len(value) < 2 or not (value.startswith('"') and value.endswith('"')):
            raise MalformedCommand("Filesystem paths must have balanced quotes.")
        value = value[1:-1]
    if not value: raise MalformedCommand("A filesystem path or name is required.")
    return value


def _split_outside_quotes(value: str, words: tuple[str, ...]) -> tuple[str, str] | None:
    quoted = False; matches = []
    lowered = value.casefold()
    for index, character in enumerate(value):
        if character == '"': quoted = not quoted
        if not quoted:
            for word in words:
                if lowered.startswith(word, index): matches.append((index, word))
    if quoted: raise MalformedCommand("Filesystem paths must have balanced quotes.")
    if not matches: return None
    if len(matches) != 1:
        raise ClarificationRequired("Quote filesystem paths containing command separators such as 'to', 'in', or 'on'.")
    index, word = matches[0]
    return value[:index], value[index + len(word):]


def _file_action(surface: str) -> Action | None:
    if match := re.fullmatch(r'open\s+(?:that|the last|last)\s+(file|folder)', surface, re.I):
        return Action(ActionType.OPEN_PATH,
                      f"recent:{'file' if match.group(1).casefold() == 'file' else 'directory'}").validate()
    if match := re.fullmatch(r'open\s+(file|folder)\s+(.+)', surface, re.I):
        reference = match.group(2).strip().casefold()
        target = f"recent:{'file' if match.group(1).casefold() == 'file' else 'directory'}" if reference in {"that", "the last", "last"} else _literal(match.group(2))
        return Action(ActionType.OPEN_PATH, target).validate()
    if match := re.fullmatch(r'delete(?:\s+(?:file|folder))?\s+(.+)', surface, re.I):
        return Action(ActionType.DELETE_PATH, _literal(match.group(1))).validate()
    if match := re.fullmatch(r'(move|copy|rename)\s+(?:file|folder)\s+(.+)', surface, re.I):
        split = _split_outside_quotes(match.group(2), (" to ",))
        if split is None: raise ClarificationRequired("Specify both source and destination using 'to'.")
        source, destination = map(_literal, split)
        if source.casefold() in {"that", "the last", "last"}:
            if match.group(1).casefold() != "copy":
                raise ClarificationRequired("Move, rename, and delete require an explicit source path.")
            source = "recent:file"
        kind = {"move": ActionType.MOVE_PATH, "copy": ActionType.COPY_PATH,
                "rename": ActionType.RENAME_PATH}[match.group(1).casefold()]
        return Action(kind, source, {"destination": destination}).validate()
    if match := re.fullmatch(r'create\s+folder(?:\s+called)?\s+(.+)', surface, re.I):
        split = _split_outside_quotes(match.group(1), (" in ", " on "))
        name, parent = (match.group(1), "desktop") if split is None else split
        return Action(ActionType.CREATE_FOLDER, _literal(parent), {"name": _literal(name)}).validate()
    return None


def parse(text: str, *, on_event=None) -> Action:
    event = on_event or (lambda _name: None)
    event("normalization_start"); command = normalize_command(text); event("normalization_complete")
    guard(command); surface, control = command.surface, command.control
    event("grammar_start")
    def done(action: Action) -> Action:
        event("grammar_complete"); return action.validate()

    if action := _file_action(surface): return done(action)
    if control in {"shutdown", "shut down", "shut down computer"}: return done(Action(ActionType.SHUTDOWN))
    if control in {"open browser", "start browser", "launch browser"}: return done(Action(ActionType.OPEN_BROWSER))
    if m := re.fullmatch(r"(?:open|go to|navigate to)\s+((?:https?://)?[^ ]+\.[^ ]+)", surface, re.I):
        kind = ActionType.OPEN_WEBSITE if control.startswith("open ") else ActionType.NAVIGATE_BROWSER
        return done(Action(kind, m.group(1)))
    if m := re.fullmatch(r"open\s+(youtube|google|github)", surface, re.I): return done(Action(ActionType.OPEN_WEBSITE, m.group(1)))
    if m := re.fullmatch(r"search\s+(?:the\s+)?web\s+for\s+(.+)", surface, re.I): return done(Action(ActionType.SEARCH_WEB, m.group(1)))
    if m := re.fullmatch(r"search\s+youtube\s+for\s+(.+)", surface, re.I): return done(Action(ActionType.SEARCH_YOUTUBE, m.group(1)))
    if m := re.fullmatch(r"play\s+(.+?)(?:\s+on\s+youtube)?", surface, re.I): return done(Action(ActionType.PLAY_YOUTUBE, m.group(1)))
    if m := re.fullmatch(r"type\s+(.+?)\s+(?:in|into)\s+(.+)", surface, re.I): return done(Action(ActionType.TYPE_IN_BROWSER, m.group(2), {"text": m.group(1)}))
    if m := re.fullmatch(r"click\s+(?:(button|link|checkbox|radio|menuitem|tab)\s+)?(.+)", surface, re.I): return done(Action(ActionType.CLICK_BROWSER_ELEMENT, m.group(2), {"role": m.group(1) or "button"}))
    if m := re.fullmatch(r"submit(?:\s+(.+))?", surface, re.I): return done(Action(ActionType.SUBMIT_BROWSER, m.group(1) or "submit", {"role": "button"}))
    if m := re.fullmatch(r"download\s+(.+)", surface, re.I): return done(Action(ActionType.DOWNLOAD_FILE, m.group(1)))

    if m := re.fullmatch(r"(.+?)\s+(?:kholo|kholna|khol\s+do)(?:\s+please)?", surface, re.I):
        return done(Action(ActionType.OPEN_APPLICATION, _trim_target(m.group(1))))
    if re.fullmatch(r"(?:isko|usko)\s+(?:thoda\s+)?chhota\s+karo", control): return done(Action(ActionType.RESIZE_WINDOW, "tracked", {"scale": .9}))
    if re.fullmatch(r"(?:isko|usko)\s+(?:thoda\s+)?bada\s+karo", control): return done(Action(ActionType.RESIZE_WINDOW, "tracked", {"scale": 1.1}))
    if m := re.fullmatch(fr"is window ko\s+({DIRECTION})\s+mein\s+le jao", control): return done(Action(ActionType.MOVE_WINDOW, "foreground", {"position": DIRECTIONS[m.group(1)]}))

    if m := re.fullmatch(fr"(?:open|launch|start|bring up)\s+(.+?){POLITE_SUFFIX}", surface, re.I):
        target = _trim_target(m.group(1)); folder = _known_folder(target)
        if folder: return done(Action(ActionType.OPEN_PATH, folder))
        if "\\" in target or ":/" in target: return done(Action(ActionType.OPEN_PATH, target))
        return done(Action(ActionType.OPEN_APPLICATION, target))
    if m := re.fullmatch(r"(?:focus|switch to)\s+(.+)", surface, re.I): return done(Action(ActionType.FOCUS_WINDOW, _trim_target(m.group(1))))
    for verb, kind in (("minimize", ActionType.MINIMIZE_WINDOW), ("maximize", ActionType.MAXIMIZE_WINDOW), ("restore", ActionType.RESTORE_WINDOW)):
        if m := re.fullmatch(fr"{verb}(?:\s+(.+?))?{POLITE_SUFFIX}", surface, re.I):
            target = _trim_target(m.group(1)) if m.group(1) else "tracked"
            if re.fullmatch(REFERENCE, target, re.I): target = _reference(target)
            return done(Action(kind, target))

    if m := re.fullmatch(fr"make\s+({REFERENCE})\s+(?:about\s+)?(?:one[- ]fifth|a fifth|20%)(?:\s+of\s+the\s+screen)?{POLITE_SUFFIX}", surface, re.I):
        return done(Action(ActionType.RESIZE_WINDOW, _reference(m.group(1)), {"screen_ratio": .2}))
    if m := re.fullmatch(fr"make\s+({REFERENCE})\s+half\s+(?:the\s+|its\s+)?size{POLITE_SUFFIX}", surface, re.I):
        return done(Action(ActionType.RESIZE_WINDOW, _reference(m.group(1)), {"scale": .5}))
    if m := re.fullmatch(fr"make\s+({REFERENCE})\s+(?:(?:{NUMBER})\s*(?:%|percent)\s+|a little\s+|slightly\s+)?(smaller|bigger|larger){POLITE_SUFFIX}", surface, re.I):
        amount_match = re.search(fr"({NUMBER})\s*(?:%|percent)", m.group(0), re.I)
        amount = _number(amount_match.group(1)) / 100 if amount_match else .1
        scale = 1 - amount if m.group(2).casefold() == "smaller" else 1 + amount
        return done(Action(ActionType.RESIZE_WINDOW, _reference(m.group(1)), {"scale": scale}))
    if m := re.fullmatch(fr"(?:shrink|reduce)\s+({REFERENCE})(?:\s+(?:a little|slightly))?{POLITE_SUFFIX}", surface, re.I): return done(Action(ActionType.RESIZE_WINDOW, _reference(m.group(1)), {"scale": .9}))
    if m := re.fullmatch(fr"(?:enlarge|grow)\s+({REFERENCE})(?:\s+(?:a little|slightly))?{POLITE_SUFFIX}", surface, re.I): return done(Action(ActionType.RESIZE_WINDOW, _reference(m.group(1)), {"scale": 1.1}))
    if m := re.fullmatch(fr"resize\s+(.+?)\s+({NUMBER})\s*(?:%|percent){POLITE_SUFFIX}", surface, re.I): return done(Action(ActionType.RESIZE_WINDOW, _trim_target(m.group(1)), {"screen_ratio": _number(m.group(2)) / 100}))

    if m := re.fullmatch(fr"(?:move|put|place)\s+({REFERENCE})(?:\s+({NUMBER})\s+pixels?)?(?:\s+slightly)?(?:\s+(?:to|in|at))?(?:\s+the)?\s+({DIRECTION}){POLITE_SUFFIX}", surface, re.I):
        params = {"position": DIRECTIONS[m.group(3).casefold()]}
        if m.group(2): params["pixels"] = _number(m.group(2))
        return done(Action(ActionType.MOVE_WINDOW, _reference(m.group(1)), params))
    if m := re.fullmatch(fr"move\s+(.+?)(?:\s+to)?(?:\s+the)?\s+({DIRECTION}){POLITE_SUFFIX}", surface, re.I): return done(Action(ActionType.MOVE_WINDOW, _trim_target(m.group(1)), {"position": DIRECTIONS[m.group(2).casefold()]}))

    if control in {"take screenshot", "take a screenshot"}: return done(Action(ActionType.TAKE_SCREENSHOT))
    if m := re.fullmatch(fr"set volume (?:to )?({NUMBER})\s*(?:%|percent)?{POLITE_SUFFIX}", surface, re.I): return done(Action(ActionType.SET_VOLUME, params={"level": _number(m.group(1))}))
    if m := re.fullmatch(fr"(?:increase|decrease|raise|lower|reduce) volume(?: by)?\s+({NUMBER})\s*(?:%|percent)?{POLITE_SUFFIX}", surface, re.I):
        sign = -1 if m.group(0).casefold().startswith(("decrease", "lower", "reduce")) else 1
        return done(Action(ActionType.CHANGE_VOLUME, params={"delta": sign * _number(m.group(1))}))
    if control in {"mute", "mute volume"}: return done(Action(ActionType.MUTE))
    if control in {"unmute", "unmute volume"}: return done(Action(ActionType.UNMUTE))
    event("grammar_complete")
    raise UnsupportedCommand(f"Unsupported or ambiguous command: {text!r}")
