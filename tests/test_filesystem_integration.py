"""Opt-in native Windows tests use disposable temporary fixtures only."""
import ctypes
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from aria.core import Action, ActionType as T, Verification
from aria.engine import Engine
from aria.filesystem import Files
from aria.permissions import ConfirmationRequired
from aria.permissions import PermissionDenied


pytestmark = [
    pytest.mark.filesystem_integration,
    pytest.mark.skipif(os.environ.get("ARIA_FILESYSTEM_INTEGRATION") != "1",
                       reason="set ARIA_FILESYSTEM_INTEGRATION=1"),
]


def confirm(engine, action):
    with pytest.raises(ConfirmationRequired) as error: engine.execute(action)
    return engine.confirm(error.value.pending.token)


def test_native_disposable_create_copy_move_and_rename(tmp_path):
    engine = Engine(files=Files(tmp_path), shutdown=Mock())
    created = engine.execute(Action(T.CREATE_FOLDER, str(tmp_path), {"name": "fixture"}))
    assert created.verification == Verification.VERIFIED
    source = tmp_path / "source.bin"; source.write_bytes(os.urandom(1024 * 1024))
    copied = tmp_path / "copied.bin"
    assert engine.execute(Action(T.COPY_PATH, str(source), {"destination": str(copied)})).verification == Verification.VERIFIED
    moved = tmp_path / "moved.bin"
    assert confirm(engine, Action(T.MOVE_PATH, str(copied), {"destination": str(moved)})).verification == Verification.VERIFIED
    renamed = tmp_path / "renamed.bin"
    assert confirm(engine, Action(T.RENAME_PATH, str(moved), {"destination": renamed.name})).verification == Verification.VERIFIED
    assert renamed.read_bytes() == source.read_bytes()


def test_native_disposable_recycle_request_is_explicitly_unverified(tmp_path):
    target = tmp_path / "aria-phase4-recycle-fixture.txt"; target.write_text("disposable")
    engine = Engine(files=Files(tmp_path), shutdown=Mock())
    result = confirm(engine, Action(T.DELETE_PATH, str(target)))
    assert result.observed and result.verification == Verification.UNVERIFIED
    assert not target.exists() and result.data["recycle_bin_verified"] is False


def test_native_sharing_violation_preserves_source_and_destination(tmp_path):
    source = tmp_path / "locked.bin"; source.write_bytes(b"locked")
    destination = tmp_path / "destination.bin"
    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.restype = ctypes.c_void_p
    handle = create_file(str(source), 0x80000000, 0, None, 3, 0x80, None)
    if handle in (None, ctypes.c_void_p(-1).value): pytest.skip("could not acquire an exclusive fixture handle")
    try:
        engine = Engine(files=Files(tmp_path), shutdown=Mock())
        with pytest.raises((PermissionDenied, PermissionError, OSError)):
            engine.execute(Action(T.COPY_PATH, str(source), {"destination": str(destination)}))
        assert source.exists() and not destination.exists()
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def test_native_cross_volume_when_explicit_disposable_root_is_available(tmp_path):
    configured = os.environ.get("ARIA_CROSS_VOLUME_ROOT")
    if not configured: pytest.skip("set ARIA_CROSS_VOLUME_ROOT to a disposable directory on another volume")
    root = Path(configured)
    if not root.is_dir() or root.stat().st_dev == tmp_path.stat().st_dev:
        pytest.skip("configured root is unavailable or not on another volume")
    destination = root / f"aria-phase4-{os.getpid()}.bin"
    source = tmp_path / "source.bin"; source.write_bytes(os.urandom(1024 * 1024))
    try:
        engine = Engine(files=Files(tmp_path), shutdown=Mock())
        result = confirm(engine, Action(T.MOVE_PATH, str(source), {"destination": str(destination)}))
        assert result.verification == Verification.VERIFIED and result.data["cross_volume"]
    finally:
        destination.unlink(missing_ok=True)
