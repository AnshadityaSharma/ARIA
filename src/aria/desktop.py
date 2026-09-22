from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
from difflib import get_close_matches
from pathlib import Path
from uuid import UUID


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


class Applications:
    def discover(self) -> dict[str, str]:
        script = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=8, check=True)
        rows = json.loads(result.stdout or "[]"); rows = [rows] if isinstance(rows, dict) else rows
        return {row["Name"].casefold(): row["AppID"] for row in rows}

    def launch(self, name: str) -> None:
        apps = self.discover(); key = name.casefold()
        exact = apps.get(key)
        if exact is None:
            hits = [(title, appid) for title, appid in apps.items() if key in title]
            if len(hits) == 1: exact = hits[0][1]
            elif close := get_close_matches(key, apps, n=2, cutoff=.78):
                if len(close) > 1 and abs(len(close[0])-len(close[1])) < 2: raise LookupError(f"Application {name!r} is ambiguous")
                exact = apps[close[0]]
            else: raise LookupError(f"Application {name!r} not found or is ambiguous")
        os.startfile(f"shell:AppsFolder\\{exact}")


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
        return Path(shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst))
    def move(self, source: str, destination: str) -> Path:
        return Path(shutil.move(self.resolve(source), self.resolve(destination)))
    def rename(self, source: str, name: str) -> Path:
        src = self.resolve(source); return src.rename(src.with_name(name))
    def delete(self, value: str) -> None:
        from send2trash import send2trash
        send2trash(str(self.resolve(value)))


def screenshot(destination: str | None = None) -> Path:
    from datetime import datetime
    from PIL import ImageGrab
    path = Path(destination) if destination else known_folder("pictures") / f"ARIA-{datetime.now():%Y%m%d-%H%M%S}.png"
    ImageGrab.grab(all_screens=True).save(path); return path


class Volume:
    def _endpoint(self):
        from pycaw.pycaw import AudioUtilities
        return AudioUtilities.GetSpeakers().EndpointVolume
    def set(self, level: int) -> int:
        level = max(0, min(100, level)); self._endpoint().SetMasterVolumeLevelScalar(level/100, None); return level
    def change(self, delta: int) -> int:
        return self.set(round(self._endpoint().GetMasterVolumeLevelScalar()*100) + delta)
    def mute(self, value: bool) -> None: self._endpoint().SetMute(value, None)
