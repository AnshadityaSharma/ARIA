from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from aria.parser import ClarificationRequired
from aria.filesystem import Files, KNOWN, known_folder


@dataclass(frozen=True, slots=True)
class Application:
    name: str
    app_id: str


def _application_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _compact_application_key(value: str) -> str:
    return "".join(character for character in _application_key(value) if character.isalnum())


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right): left, right = right, left
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    index_left = index_right = differences = 0
    while index_left < len(left) and index_right < len(right):
        if left[index_left] == right[index_right]:
            index_left += 1; index_right += 1
        else:
            differences += 1; index_right += 1
            if differences > 1: return False
    return True


class Applications:
    cache_seconds = 2.0

    def __init__(self):
        self._cache: tuple[float, tuple[Application, ...]] | None = None

    def discover(self) -> list[Application]:
        if self._cache is not None and time.monotonic() - self._cache[0] < self.cache_seconds:
            return list(self._cache[1])
        script = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=8, check=True)
        rows = json.loads(result.stdout or "[]"); rows = [rows] if isinstance(rows, dict) else rows
        if not isinstance(rows, list):
            raise OSError("Windows returned an invalid Start Apps response")
        applications = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("Name"), str) or not isinstance(row.get("AppID"), str):
                raise OSError("Windows returned an invalid Start Apps record")
            name, app_id = row["Name"].strip(), row["AppID"].strip()
            if not name or not app_id:
                raise OSError("Windows returned an empty Start Apps record")
            applications.append(Application(name, app_id))
        self._cache = (time.monotonic(), tuple(applications))
        return applications

    @staticmethod
    def _unique(matches: list[Application], query: str) -> Application:
        if not matches:
            raise ClarificationRequired(f"Application {query!r} was not found")
        if len(matches) != 1:
            names = ", ".join(sorted({item.name for item in matches})[:5])
            raise ClarificationRequired(f"Application {query!r} is ambiguous: {names}")
        return matches[0]

    def resolve(self, query: str) -> Application:
        key = _application_key(query)
        if not key:
            raise LookupError("Application name is empty")
        applications = self.discover()
        exact = [item for item in applications if _application_key(item.name) == key]
        if exact:
            return self._unique(exact, query)
        compact = _compact_application_key(query)
        compact_exact = [item for item in applications
                         if _compact_application_key(item.name) == compact]
        if compact_exact:
            return self._unique(compact_exact, query)
        partial = [item for item in applications if key in _application_key(item.name)]
        if partial:
            return self._unique(partial, query)
        # ASR/spelling recovery is intentionally narrow and derived entirely
        # from live discovery. It never applies to paths, URLs, or payloads.
        if " " not in key and len(compact) >= 5 and compact.isalnum():
            near = [item for item in applications
                    if _edit_distance_at_most_one(compact, _compact_application_key(item.name))]
            if near:
                return self._unique(near, query)
        return self._unique([], query)

    def recheck(self, application: Application) -> Application:
        self._cache = None
        matches = [item for item in self.discover()
                   if item.name == application.name and item.app_id == application.app_id]
        if len(matches) != 1:
            raise LookupError("Application identity changed before launch")
        return matches[0]

    def launch(self, name: str | Application) -> Application:
        application = self.resolve(name) if isinstance(name, str) else name
        os.startfile(f"shell:AppsFolder\\{application.app_id}")
        return application


@dataclass(frozen=True, slots=True)
class ScreenshotReceipt:
    path: Path
    width: int
    height: int


def _parent_identity(parent: Path) -> tuple[int, int]:
    Files.ensure_no_reparse(parent)
    if not parent.is_dir():
        raise NotADirectoryError(parent)
    info = parent.stat()
    return info.st_dev, info.st_ino


def _virtual_desktop_size() -> tuple[int, int] | None:
    if os.name != "nt":
        return None
    import ctypes
    user32 = ctypes.windll.user32
    try:
        set_context = user32.SetThreadDpiAwarenessContext
    except AttributeError:
        return None
    set_context.argtypes = [ctypes.c_void_p]
    set_context.restype = ctypes.c_void_p
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    previous = None
    for awareness in (-4, -3, -2):
        previous = set_context(ctypes.c_void_p(awareness))
        if previous:
            break
    if not previous:
        return None
    try:
        width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        return (width, height) if width > 0 and height > 0 else None
    finally:
        set_context(previous)


def _publish_screenshot(stage: Path, destination: Path) -> None:
    # On Windows os.rename uses no-replace semantics. The stage shares the
    # destination directory, so publication is atomic on its filesystem.
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    os.rename(stage, destination)


def screenshot(destination: str | Path, *, expected_parent_identity: tuple[int, int] | None = None) -> ScreenshotReceipt:
    from PIL import Image, ImageGrab
    path = Path(destination)
    if path.suffix.casefold() != ".png":
        raise ValueError("Screenshot destination must be a PNG path")
    identity = _parent_identity(path.parent)
    if expected_parent_identity is not None and identity != expected_parent_identity:
        raise OSError("Screenshot parent changed before capture")
    if os.path.lexists(path):
        raise FileExistsError(path)
    geometry_before = _virtual_desktop_size()
    descriptor, stage_name = tempfile.mkstemp(prefix=".aria-screenshot-", suffix=".png", dir=path.parent)
    stage = Path(stage_name)
    stage_info = os.fstat(descriptor)
    stage_identity = (stage_info.st_dev, stage_info.st_ino)
    try:
        with os.fdopen(descriptor, "wb") as output:
            capture = ImageGrab.grab(all_screens=True)
            try:
                capture.save(output, format="PNG")
            finally:
                capture.close()
        with Image.open(stage) as check:
            if check.format != "PNG":
                raise ValueError("Screenshot output is not PNG")
            check.verify()
        with Image.open(stage) as check:
            check.load()
            width, height = check.size
        if width <= 0 or height <= 0:
            raise ValueError("Screenshot dimensions are invalid")
        geometry_after = _virtual_desktop_size()
        if geometry_before != geometry_after:
            raise OSError("Virtual desktop geometry changed during capture")
        if geometry_before is not None and (width, height) != geometry_before:
            raise ValueError("Screenshot dimensions do not match the virtual desktop")
        if _parent_identity(path.parent) != identity:
            raise OSError("Screenshot parent changed before publication")
        current_stage = stage.lstat()
        if (current_stage.st_dev, current_stage.st_ino) != stage_identity:
            raise OSError("Screenshot staging file changed before publication")
        if os.path.lexists(path):
            raise FileExistsError(path)
        _publish_screenshot(stage, path)
        try:
            published = path.lstat()
        except OSError as exc:
            raise OSError("Published screenshot could not be verified") from exc
        if (published.st_dev, published.st_ino) != stage_identity or published.st_size <= 0:
            raise OSError("Published screenshot identity or size could not be verified")
        return ScreenshotReceipt(path, width, height)
    finally:
        if os.path.lexists(stage) and (stage.lstat().st_dev, stage.lstat().st_ino) == stage_identity:
            stage.unlink()


@dataclass(frozen=True, slots=True)
class AudioState:
    level: int
    muted: bool
    endpoint_id: str


class Volume:
    def _device(self):
        from pycaw.pycaw import AudioUtilities
        try:
            device = AudioUtilities.GetSpeakers()
            endpoint = device.EndpointVolume if device is not None else None
        except Exception as exc:
            raise OSError("Default audio output device is unavailable") from exc
        if device is None or not device.id or endpoint is None:
            raise OSError("No default audio output device is available")
        return device.id, endpoint

    def _readback(self, endpoint_id, endpoint) -> AudioState:
        try:
            scalar = float(endpoint.GetMasterVolumeLevelScalar())
            muted = bool(endpoint.GetMute())
        except Exception as exc:
            raise OSError("Audio readback failed; the write may have completed") from exc
        if not math.isfinite(scalar) or not 0 <= scalar <= 1:
            raise OSError("Audio endpoint returned an invalid volume")
        current_id, _ = self._device()
        if current_id != endpoint_id:
            raise OSError("Default audio endpoint changed; the operation may have completed on the previous device")
        return AudioState(round(scalar * 100), muted, endpoint_id)

    def set(self, level: int) -> AudioState:
        requested = max(0, min(100, level))
        endpoint_id, endpoint = self._device()
        try:
            endpoint.SetMasterVolumeLevelScalar(requested / 100, None)
        except Exception as exc:
            raise OSError("Audio volume write failed; the state may have changed") from exc
        observed = self._readback(endpoint_id, endpoint)
        if observed.level != requested:
            raise OSError(f"Volume write could not be verified: requested {requested}%, observed {observed.level}%")
        return observed

    def change(self, delta: int) -> AudioState:
        endpoint_id, endpoint = self._device()
        try:
            before = float(endpoint.GetMasterVolumeLevelScalar())
        except Exception as exc:
            raise OSError("Current audio volume could not be read") from exc
        if not math.isfinite(before) or not 0 <= before <= 1:
            raise OSError("Audio endpoint returned an invalid volume")
        requested = max(0, min(100, round(before * 100) + delta))
        try:
            endpoint.SetMasterVolumeLevelScalar(requested / 100, None)
        except Exception as exc:
            raise OSError("Audio volume write failed; the state may have changed") from exc
        observed = self._readback(endpoint_id, endpoint)
        if observed.level != requested:
            raise OSError(f"Volume change could not be verified: requested {requested}%, observed {observed.level}%")
        return observed

    def mute(self, value: bool) -> AudioState:
        endpoint_id, endpoint = self._device()
        try:
            endpoint.SetMute(value, None)
        except Exception as exc:
            raise OSError("Audio mute write failed; the state may have changed") from exc
        observed = self._readback(endpoint_id, endpoint)
        if observed.muted != value:
            raise OSError(f"Mute write could not be verified: requested {value}, observed {observed.muted}")
        return observed


def shutdown_computer():
    # Fixed system capability: never accepts arbitrary shell arguments.
    executable = Path(os.environ["SystemRoot"]) / "System32" / "shutdown.exe"
    subprocess.run([str(executable), "/s", "/t", "0"], check=True, timeout=10)
