"""Deterministic local filesystem resolution, identity, and operations."""
from __future__ import annotations

import ctypes
import hashlib
import os
import re
import shutil
import stat as stat_module
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from aria.parser import ClarificationRequired


KNOWN = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}
ALIASES = {"document": "documents", "download": "downloads", "picture": "pictures", "video": "videos"}
REPARSE_ATTRIBUTE = 0x400
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def known_folder(name: str) -> Path:
    key = ALIASES.get(name.casefold(), name.casefold())
    guid = UUID(KNOWN[key]); raw = (ctypes.c_ubyte * 16).from_buffer_copy(guid.bytes_le)
    ptr = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(raw), 0, None, ctypes.byref(ptr)):
        raise OSError(f"Cannot resolve {name}")
    try: return Path(ptr.value)
    finally: ctypes.windll.ole32.CoTaskMemFree(ptr)


class FilesystemIdentityError(OSError): pass


@dataclass(frozen=True, slots=True)
class PathIdentity:
    device: int
    file_id: int
    mode: int


@dataclass(frozen=True, slots=True)
class PathSnapshot:
    path: str
    parent_identity: PathIdentity
    identity: PathIdentity
    kind: str
    size: int
    mtime_ns: int
    ctime_ns: int
    reparse: bool
    metadata_sha256: str | None = None
    content_sha256: str | None = None
    entry_count: int = 1
    total_bytes: int = 0


@dataclass(frozen=True, slots=True)
class OperationReceipt:
    path: Path
    cross_volume: bool = False


def _identity(info: os.stat_result) -> PathIdentity:
    device, file_id = int(info.st_dev), int(info.st_ino)
    if device == 0 or file_id == 0:
        raise FilesystemIdentityError("Windows did not provide a stable filesystem identity")
    return PathIdentity(device, file_id, stat_module.S_IFMT(info.st_mode))


def _is_reparse(info: os.stat_result) -> bool:
    return stat_module.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & REPARSE_ATTRIBUTE)


def _kind(info: os.stat_result) -> str:
    if stat_module.S_ISREG(info.st_mode): return "file"
    if stat_module.S_ISDIR(info.st_mode): return "directory"
    if stat_module.S_ISLNK(info.st_mode): return "symlink"
    return "other"


def _hash_file(path: Path, digest) -> int:
    total = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk); total += len(chunk)
    return total


def snapshot(path: str | Path, *, recursive_metadata: bool = False,
             content: bool = False, reject_reparse: bool = False) -> PathSnapshot:
    target = Path(path)
    info, parent_info = target.lstat(), target.parent.lstat()
    reparse, kind = _is_reparse(info), _kind(info)
    if reject_reparse and reparse:
        raise FilesystemIdentityError(f"Reparse-point targets are not supported: {target}")
    if kind not in {"file", "directory"}:
        raise FilesystemIdentityError(f"Unsupported filesystem target type: {target}")
    metadata = hashlib.sha256() if recursive_metadata or content else None
    contents = hashlib.sha256() if content else None
    entries, total_bytes = 1, 0

    def record(relative: str, item: Path, item_info: os.stat_result) -> None:
        nonlocal entries, total_bytes
        item_reparse, item_kind = _is_reparse(item_info), _kind(item_info)
        if reject_reparse and item_reparse:
            raise FilesystemIdentityError(f"Reparse point inside filesystem target: {item}")
        if item_kind not in {"file", "directory"}:
            raise FilesystemIdentityError(f"Unsupported entry inside filesystem target: {item}")
        entries += 1
        stable_size = item_info.st_size if item_kind == "file" else 0
        stable_mtime = item_info.st_mtime_ns if item_kind == "file" else 0
        marker = f"{relative}\0{item_kind}\0{item_info.st_dev}\0{item_info.st_ino}\0{stable_size}\0{stable_mtime}\n".encode("utf-8", "surrogatepass")
        if metadata is not None: metadata.update(marker)
        if contents is not None:
            contents.update(f"{relative}\0{item_kind}\0".encode("utf-8", "surrogatepass"))
            if item_kind == "file": total_bytes += _hash_file(item, contents)

    if metadata is not None:
        stable_size = info.st_size if kind == "file" else 0
        stable_mtime = info.st_mtime_ns if kind == "file" else 0
        metadata.update(f".\0{kind}\0{info.st_dev}\0{info.st_ino}\0{stable_size}\0{stable_mtime}\n".encode())
    if contents is not None:
        contents.update(f".\0{kind}\0".encode())
        if kind == "file": total_bytes = _hash_file(target, contents)
    if kind == "directory" and (recursive_metadata or content):
        def visit(directory: Path, relative: Path) -> None:
            with os.scandir(directory) as scan:
                children = sorted(scan, key=lambda item: item.name.casefold())
            for child in children:
                child_path = Path(child.path); child_relative = (relative / child.name).as_posix()
                child_info = child.stat(follow_symlinks=False)
                record(child_relative, child_path, child_info)
                if stat_module.S_ISDIR(child_info.st_mode) and not _is_reparse(child_info):
                    visit(child_path, relative / child.name)
        visit(target, Path())
    return PathSnapshot(
        str(target), _identity(parent_info), _identity(info), kind, int(info.st_size),
        int(info.st_mtime_ns), int(info.st_ctime_ns), reparse,
        metadata.hexdigest() if metadata is not None else None,
        contents.hexdigest() if contents is not None else None,
        entries, total_bytes,
    )


def same_content(left: PathSnapshot, right: PathSnapshot) -> bool:
    return (left.kind, left.content_sha256, left.entry_count, left.total_bytes) == (
        right.kind, right.content_sha256, right.entry_count, right.total_bytes)


def same_snapshot(left: PathSnapshot, right: PathSnapshot) -> bool:
    """Compare stable target evidence; Windows change-time readings are advisory."""
    if left.kind == right.kind == "directory" and left.metadata_sha256 is not None and right.metadata_sha256 is not None:
        return (
            left.path, left.parent_identity, left.identity, left.kind, left.reparse,
            left.metadata_sha256, left.content_sha256, left.entry_count, left.total_bytes,
        ) == (
            right.path, right.parent_identity, right.identity, right.kind, right.reparse,
            right.metadata_sha256, right.content_sha256, right.entry_count, right.total_bytes,
        )
    return (
        left.path, left.parent_identity, left.identity, left.kind, left.size,
        left.mtime_ns, left.reparse, left.metadata_sha256, left.content_sha256,
        left.entry_count, left.total_bytes,
    ) == (
        right.path, right.parent_identity, right.identity, right.kind, right.size,
        right.mtime_ns, right.reparse, right.metadata_sha256, right.content_sha256,
        right.entry_count, right.total_bytes,
    )


def same_metadata(left: PathSnapshot, right: PathSnapshot) -> bool:
    common = (
        left.path, left.parent_identity, left.identity, left.kind, left.size,
        left.mtime_ns, left.reparse,
    ) == (
        right.path, right.parent_identity, right.identity, right.kind, right.size,
        right.mtime_ns, right.reparse,
    )
    if not common: return False
    if left.kind == right.kind == "directory":
        return (left.metadata_sha256, left.entry_count) == (right.metadata_sha256, right.entry_count)
    return True


def snapshot_differences(left: PathSnapshot, right: PathSnapshot) -> tuple[str, ...]:
    ignored = {"ctime_ns"}
    return tuple(field for field in PathSnapshot.__dataclass_fields__
                 if field not in ignored and getattr(left, field) != getattr(right, field))


class PathResolver:
    def __init__(self, base_directory: str | Path | None = None, known_provider=known_folder):
        self.base_directory = Path(os.path.abspath(os.fspath(base_directory or Path.cwd())))
        self.known_provider = known_provider

    @staticmethod
    def _validate(value: str) -> str:
        if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Path must be a non-empty printable string")
        value = value.strip().strip('"'); lowered = value.casefold()
        if lowered.startswith("\\\\"):
            raise ValueError("Network and device paths are outside Phase 4")
        if "*" in value or "?" in value: raise ValueError("Wildcard paths are not accepted")
        drive, tail = os.path.splitdrive(value)
        if ":" in tail: raise ValueError("Alternate data stream paths are not accepted")
        for part in re.split(r"[\\/]", tail):
            if not part or part in {".", ".."}: continue
            if part.endswith((" ", ".")) or part.split(".", 1)[0].upper() in RESERVED:
                raise ValueError(f"Invalid Windows path component: {part!r}")
        if drive and not os.path.isabs(value): raise ValueError("Drive-relative paths are not accepted")
        return value

    def _known_scoped(self, value: str) -> Path | None:
        parts = re.split(r"[\\/]", value, maxsplit=1)
        key = ALIASES.get(parts[0].casefold(), parts[0].casefold())
        if key not in KNOWN: return None
        root = self.known_provider(key)
        return root if len(parts) == 1 else root / parts[1]

    def destination(self, value: str) -> Path:
        value = self._validate(value); known = self._known_scoped(value)
        if known is not None: return Path(os.path.abspath(known))
        expanded = Path(os.path.expanduser(value))
        target = expanded if expanded.is_absolute() else self.base_directory / expanded
        return Path(os.path.abspath(target))

    def existing(self, value: str) -> Path:
        value = self._validate(value); known = self._known_scoped(value)
        expanded_text = os.path.expanduser(value)
        explicit = known is not None or os.path.isabs(expanded_text) or any(c in value for c in "\\/") or value.startswith((".", "~"))
        if explicit:
            raw = known if known is not None else Path(expanded_text)
            target = Path(os.path.abspath(raw if raw.is_absolute() else self.base_directory / raw))
            if not target.exists(): raise FileNotFoundError(target)
            return target
        roots = [self.base_directory]
        for key in KNOWN:
            try: roots.append(Path(self.known_provider(key)))
            except OSError: continue
        matches, seen = [], set()
        for root in roots:
            candidate = root / value
            if candidate.exists():
                normalized = os.path.normcase(os.path.abspath(candidate))
                if normalized not in seen:
                    seen.add(normalized); matches.append(Path(os.path.abspath(candidate)))
        if not matches: raise FileNotFoundError(value)
        if len(matches) != 1:
            raise ClarificationRequired(f"Path {value!r} is ambiguous: {', '.join(str(path) for path in matches[:5])}")
        return matches[0]


class Files:
    def __init__(self, base_directory: str | Path | None = None, *, resolver: PathResolver | None = None,
                 rename_operation=os.rename):
        self.resolver = resolver or PathResolver(base_directory)
        self._rename_operation = rename_operation

    def resolve(self, value: str) -> Path: return self.resolver.existing(value)
    def resolve_destination(self, value: str) -> Path: return self.resolver.destination(value)
    @staticmethod
    def snapshot(path, **options) -> PathSnapshot: return snapshot(path, **options)

    @staticmethod
    def ensure_no_reparse(path: str | Path, *, include_leaf: bool = True) -> None:
        target = Path(path); current = target if include_leaf else target.parent; chain = []
        while current != current.parent: chain.append(current); current = current.parent
        for component in reversed(chain):
            if component.exists() and _is_reparse(component.lstat()):
                raise FilesystemIdentityError(f"Reparse-point traversal is not supported: {component}")

    def create_folder(self, parent: str, name: str) -> OperationReceipt:
        path = Path(parent) / name; os.mkdir(path); return OperationReceipt(path)

    def open(self, value: str | Path) -> Path:
        path = Path(value)
        if not path.exists(): raise FileNotFoundError(path)
        os.startfile(path); return path

    @staticmethod
    def _copy_new(source: Path, destination: Path) -> None:
        if source.is_dir(): shutil.copytree(source, destination, copy_function=shutil.copy2)
        else:
            with source.open("rb") as reader, destination.open("xb") as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
            shutil.copystat(source, destination, follow_symlinks=False)

    @staticmethod
    def _remove(path: Path) -> None:
        if path.is_dir(): shutil.rmtree(path)
        else: path.unlink()

    def rollback_created(self, path: str | Path, expected: PathSnapshot) -> bool:
        target = Path(path)
        if not target.exists(): return True
        current = snapshot(target,
                           recursive_metadata=expected.metadata_sha256 is not None,
                           content=expected.content_sha256 is not None,
                           reject_reparse=True)
        if not same_snapshot(current, expected): return False
        self._remove(target)
        return not target.exists()

    def rollback_move(self, destination: str | Path, source: str | Path,
                      expected: PathSnapshot) -> bool:
        destination_path, source_path = Path(destination), Path(source)
        if source_path.exists() or not destination_path.exists(): return False
        current = snapshot(destination_path,
                           recursive_metadata=expected.metadata_sha256 is not None,
                           content=expected.content_sha256 is not None,
                           reject_reparse=True)
        if not same_snapshot(current, expected): return False
        self._rename_operation(destination_path, source_path)
        return source_path.exists() and not destination_path.exists()

    def copy(self, source: str, destination: str) -> OperationReceipt:
        source_path, destination_path = Path(source), Path(destination)
        self.ensure_no_reparse(source_path); self.ensure_no_reparse(destination_path, include_leaf=False)
        if destination_path.exists(): raise FileExistsError(destination_path)
        self._copy_new(source_path, destination_path)
        return OperationReceipt(destination_path)

    def move(self, source: str, destination: str) -> OperationReceipt:
        source_path, destination_path = Path(source), Path(destination)
        self.ensure_no_reparse(source_path); self.ensure_no_reparse(destination_path, include_leaf=False)
        if destination_path.exists(): raise FileExistsError(destination_path)
        cross_volume = snapshot(source_path).identity.device != snapshot(destination_path.parent).identity.device
        if not cross_volume:
            self._rename_operation(source_path, destination_path)
            return OperationReceipt(destination_path, False)
        before = snapshot(source_path, recursive_metadata=True, content=True, reject_reparse=True)
        self._copy_new(source_path, destination_path)
        after = snapshot(destination_path, recursive_metadata=True, content=True, reject_reparse=True)
        if not same_content(before, after):
            self.rollback_created(destination_path, after)
            raise OSError("Cross-volume copy verification failed; source was preserved")
        self._remove(source_path)
        return OperationReceipt(destination_path, True)

    def rename(self, source: str, name: str) -> OperationReceipt:
        source_path = Path(source); destination = source_path.with_name(name)
        self.ensure_no_reparse(source_path); self.ensure_no_reparse(destination, include_leaf=False)
        if destination.exists(): raise FileExistsError(destination)
        self._rename_operation(source_path, destination)
        return OperationReceipt(destination)

    def delete(self, value: str) -> None:
        path = Path(value); self.ensure_no_reparse(path)
        from send2trash import send2trash
        send2trash(str(path))
