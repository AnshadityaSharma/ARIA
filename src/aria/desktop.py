from __future__ import annotations

import json
import os
import subprocess
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
