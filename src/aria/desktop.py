from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
from aria.parser import ClarificationRequired


KNOWN = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641", "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B", "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}


def known_folder(name: str) -> Path:
    guid = UUID(KNOWN[name.casefold()]); raw = (ctypes.c_ubyte * 16).from_buffer_copy(guid.bytes_le)
    ptr = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(raw), 0, None, ctypes.byref(ptr)):
        raise OSError(f"Cannot resolve {name}")
    try: return Path(ptr.value)
    finally: ctypes.windll.ole32.CoTaskMemFree(ptr)


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


class Files:
    def resolve(self, value: str) -> Path:
        return known_folder(value) if value.casefold() in KNOWN else Path(value).expanduser().resolve()
    def create_folder(self, parent: str, name: str) -> Path:
        if Path(name).name != name: raise ValueError("Folder name must not contain a path")
        path = self.resolve(parent) / name; path.mkdir(exist_ok=False); return path
    def open(self, value: str) -> Path:
        path = self.resolve(value)
        if not path.exists(): raise FileNotFoundError(path)
        os.startfile(path); return path
    def copy(self, source: str, destination: str) -> Path:
        src, dst = self.resolve(source), self.resolve(destination)
        if dst.exists(): raise FileExistsError(dst)
        if src.is_dir(): return Path(shutil.copytree(src, dst))
        with src.open("rb") as reader, dst.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        return dst
    def move(self, source: str, destination: str) -> Path:
        if self.resolve(destination).exists(): raise FileExistsError(destination)
        return Path(shutil.move(self.resolve(source), self.resolve(destination)))
    def rename(self, source: str, name: str) -> Path:
        src = self.resolve(source)
        if src.with_name(name).exists(): raise FileExistsError(name)
        return src.rename(src.with_name(name))
    def delete(self, value: str) -> None:
        from send2trash import send2trash
        send2trash(str(self.resolve(value)))


def screenshot(destination: str | None = None) -> Path:
    from datetime import datetime
    from PIL import ImageGrab
    path = Path(destination) if destination else known_folder("pictures") / f"ARIA-{datetime.now():%Y%m%d-%H%M%S}.png"
    with path.open("xb") as destination_file:
        ImageGrab.grab(all_screens=True).save(destination_file, format="PNG")
    return path


class Volume:
    def _endpoint(self):
        from pycaw.pycaw import AudioUtilities
        return AudioUtilities.GetSpeakers().EndpointVolume
    def set(self, level: int) -> int:
        level = max(0, min(100, level)); self._endpoint().SetMasterVolumeLevelScalar(level/100, None); return level
    def change(self, delta: int) -> int:
        return self.set(round(self._endpoint().GetMasterVolumeLevelScalar()*100) + delta)
    def mute(self, value: bool) -> None: self._endpoint().SetMute(value, None)


def shutdown_computer():
    # Fixed system capability: never accepts arbitrary shell arguments.
    executable = Path(os.environ["SystemRoot"]) / "System32" / "shutdown.exe"
    subprocess.run([str(executable), "/s", "/t", "0"], check=True, timeout=10)
