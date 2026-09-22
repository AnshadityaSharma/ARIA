from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


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


class Risk(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


RISK = {kind: Risk.NONE for kind in ActionType} | {
    ActionType.TAKE_SCREENSHOT: Risk.LOW,
    ActionType.COPY_PATH: Risk.LOW,
    ActionType.MOVE_PATH: Risk.MEDIUM,
    ActionType.RENAME_PATH: Risk.MEDIUM,
    ActionType.DELETE_PATH: Risk.HIGH,
}


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
    params: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> Action:
        if self.kind == ActionType.OPEN_APPLICATION and not self.target:
            raise ValueError("Application name is required")
        if self.kind == ActionType.RESIZE_WINDOW:
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
        if self.handle == handle and self.geometry != geometry: self.previous_geometry = self.geometry
        self.handle, self.title, self.geometry = handle, title, geometry
        if action is not None: self.last_action = action


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
