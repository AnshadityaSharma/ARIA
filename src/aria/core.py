from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from types import MappingProxyType
from collections.abc import Mapping
import math


class ActionType(StrEnum):
    OPEN_APPLICATION = "OPEN_APPLICATION"
    FOCUS_WINDOW = "FOCUS_WINDOW"
    MINIMIZE_WINDOW = "MINIMIZE_WINDOW"
    MAXIMIZE_WINDOW = "MAXIMIZE_WINDOW"
    RESTORE_WINDOW = "RESTORE_WINDOW"
    RESIZE_WINDOW = "RESIZE_WINDOW"
    MOVE_WINDOW = "MOVE_WINDOW"
    CREATE_FOLDER = "CREATE_FOLDER"
    OPEN_PATH = "OPEN_PATH"
    COPY_PATH = "COPY_PATH"
    MOVE_PATH = "MOVE_PATH"
    RENAME_PATH = "RENAME_PATH"
    DELETE_PATH = "DELETE_PATH"
    TAKE_SCREENSHOT = "TAKE_SCREENSHOT"
    SET_VOLUME = "SET_VOLUME"
    CHANGE_VOLUME = "CHANGE_VOLUME"
    MUTE = "MUTE"
    UNMUTE = "UNMUTE"
    SHUTDOWN = "SHUTDOWN"
    OPEN_BROWSER = "OPEN_BROWSER"
    OPEN_WEBSITE = "OPEN_WEBSITE"
    NAVIGATE_BROWSER = "NAVIGATE_BROWSER"
    SEARCH_WEB = "SEARCH_WEB"
    SEARCH_YOUTUBE = "SEARCH_YOUTUBE"
    PLAY_YOUTUBE = "PLAY_YOUTUBE"
    TYPE_IN_BROWSER = "TYPE_IN_BROWSER"
    CLICK_BROWSER_ELEMENT = "CLICK_BROWSER_ELEMENT"
    SUBMIT_BROWSER = "SUBMIT_BROWSER"
    DOWNLOAD_FILE = "DOWNLOAD_FILE"


class Risk(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


RISK = MappingProxyType({
    ActionType.OPEN_APPLICATION: Risk.NONE,
    ActionType.FOCUS_WINDOW: Risk.NONE,
    ActionType.MINIMIZE_WINDOW: Risk.NONE,
    ActionType.MAXIMIZE_WINDOW: Risk.NONE,
    ActionType.RESTORE_WINDOW: Risk.NONE,
    ActionType.RESIZE_WINDOW: Risk.NONE,
    ActionType.MOVE_WINDOW: Risk.NONE,
    ActionType.OPEN_PATH: Risk.NONE,
    ActionType.SET_VOLUME: Risk.NONE,
    ActionType.CHANGE_VOLUME: Risk.NONE,
    ActionType.MUTE: Risk.NONE,
    ActionType.UNMUTE: Risk.NONE,
    ActionType.CREATE_FOLDER: Risk.LOW,
    ActionType.TAKE_SCREENSHOT: Risk.LOW,
    ActionType.COPY_PATH: Risk.LOW,
    ActionType.MOVE_PATH: Risk.MEDIUM,
    ActionType.RENAME_PATH: Risk.MEDIUM,
    ActionType.DELETE_PATH: Risk.HIGH,
    ActionType.SHUTDOWN: Risk.HIGH,
    ActionType.OPEN_BROWSER: Risk.NONE,
    ActionType.OPEN_WEBSITE: Risk.NONE,
    ActionType.NAVIGATE_BROWSER: Risk.NONE,
    ActionType.SEARCH_WEB: Risk.NONE,
    ActionType.SEARCH_YOUTUBE: Risk.NONE,
    ActionType.PLAY_YOUTUBE: Risk.NONE,
    ActionType.TYPE_IN_BROWSER: Risk.NONE,
    ActionType.CLICK_BROWSER_ELEMENT: Risk.LOW,
    ActionType.SUBMIT_BROWSER: Risk.MEDIUM,
    ActionType.DOWNLOAD_FILE: Risk.LOW,
})


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class Action:
    kind: ActionType
    target: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.params, Mapping):
            raise ValueError("Action parameters must be a mapping")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))

    def validate(self) -> Action:
        if not isinstance(self.kind, ActionType):
            raise ValueError("Unsupported action")
        if self.target is not None and (not isinstance(self.target, str) or not self.target.strip() or any(ord(c) < 32 for c in self.target)):
            raise ValueError("Invalid action target")
        required = {ActionType.OPEN_APPLICATION, ActionType.CREATE_FOLDER, ActionType.OPEN_PATH,
                    ActionType.COPY_PATH, ActionType.MOVE_PATH, ActionType.RENAME_PATH, ActionType.DELETE_PATH,
                    ActionType.OPEN_WEBSITE, ActionType.NAVIGATE_BROWSER, ActionType.SEARCH_WEB,
                    ActionType.SEARCH_YOUTUBE, ActionType.PLAY_YOUTUBE, ActionType.TYPE_IN_BROWSER,
                    ActionType.CLICK_BROWSER_ELEMENT, ActionType.SUBMIT_BROWSER, ActionType.DOWNLOAD_FILE}
        if self.kind in required and not self.target:
            raise ValueError("Action requires a target")
        fields = {
            ActionType.RESIZE_WINDOW: {"scale", "screen_ratio"}, ActionType.MOVE_WINDOW: {"position", "pixels"},
            ActionType.CREATE_FOLDER: {"name"}, ActionType.COPY_PATH: {"destination"},
            ActionType.MOVE_PATH: {"destination"}, ActionType.RENAME_PATH: {"destination"},
            ActionType.SET_VOLUME: {"level"}, ActionType.CHANGE_VOLUME: {"delta"},
            ActionType.TYPE_IN_BROWSER: {"text"}, ActionType.CLICK_BROWSER_ELEMENT: {"role"},
            ActionType.SUBMIT_BROWSER: {"role"}, ActionType.DOWNLOAD_FILE: {"destination"},
        }
        if set(self.params) - fields.get(self.kind, set()):
            raise ValueError("Unexpected action parameters")
        if any(type(v) not in (str, int, float) for v in self.params.values()):
            raise ValueError("Action parameters must be scalar values")
        for key in ("destination", "name"):
            if key in self.params or (key == "destination" and self.kind in {ActionType.COPY_PATH, ActionType.MOVE_PATH, ActionType.RENAME_PATH}) or (key == "name" and self.kind == ActionType.CREATE_FOLDER):
                value = self.params.get(key)
                if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
                    raise ValueError(f"Missing or invalid {key}")
        if self.kind == ActionType.TYPE_IN_BROWSER:
            value = self.params.get("text")
            if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
                raise ValueError("Browser text must be a non-empty printable string")
        if self.kind in {ActionType.CLICK_BROWSER_ELEMENT, ActionType.SUBMIT_BROWSER}:
            role = self.params.get("role", "button")
            if role not in {"button", "link", "checkbox", "radio", "menuitem", "tab"}:
                raise ValueError("Unsupported browser element role")
        if self.kind == ActionType.SHUTDOWN and self.target is not None:
            raise ValueError("Shutdown does not accept a target")
        for key, low, high in (("level", 0, 100), ("delta", -100, 100)):
            if key in fields.get(self.kind, set()):
                if type(self.params.get(key)) is not int or not low <= self.params[key] <= high:
                    raise ValueError(f"{key} must be an integer between {low} and {high}")
        if self.kind == ActionType.MOVE_WINDOW:
            if self.params.get("position") not in {"top_left", "top_right", "bottom_left", "bottom_right", "center", "top", "bottom", "left", "right", "up", "down"}:
                raise ValueError("Invalid window position")
            if "pixels" in self.params and (type(self.params["pixels"]) is not int or not 1 <= self.params["pixels"] <= 10000):
                raise ValueError("Invalid movement distance")
        if self.kind == ActionType.OPEN_APPLICATION and not self.target:
            raise ValueError("Application name is required")
        if self.kind == ActionType.RESIZE_WINDOW:
            if len(self.params) != 1 or any(type(v) not in (int, float) or not math.isfinite(v) for v in self.params.values()):
                raise ValueError("Resize requires exactly one finite numeric ratio")
            scale = self.params.get("scale")
            ratio = self.params.get("screen_ratio")
            if scale is None and ratio is None:
                raise ValueError("Resize requires scale or screen_ratio")
            if scale is not None and not 0.1 <= float(scale) <= 3:
                raise ValueError("Scale must be between 0.1 and 3")
            if ratio is not None and not 0.1 <= float(ratio) <= 1:
                raise ValueError("Screen ratio must be between 10% and 100%")
        return self


@dataclass(slots=True)
class WindowState:
    handle: int | None = None
    title: str | None = None
    geometry: Rect | None = None
    previous_geometry: Rect | None = None
    last_action: ActionType | None = None

    def update(self, handle: int, title: str, geometry: Rect, action: ActionType | None = None) -> None:
        if self.handle != handle: self.previous_geometry = None
        if self.handle == handle and self.geometry != geometry: self.previous_geometry = self.geometry
        self.handle, self.title, self.geometry = handle, title, geometry
        if action is not None: self.last_action = action


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
