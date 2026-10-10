"""Controlled Phase 5 media tests; never change the real speaker state."""
import errno
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from aria import desktop
from aria.core import Action, ActionType as T, Verification
from aria.engine import Engine
from aria.permissions import ConfirmationRequired, PermissionDenied, PermissionEngine


def image_capture(monkeypatch, size=(48, 32)):
    capture = Mock(side_effect=lambda **_kwargs: Image.new("RGB", size, "navy"))
    monkeypatch.setattr("PIL.ImageGrab.grab", capture)
    monkeypatch.setattr(desktop, "_virtual_desktop_size", lambda: size)
    return capture


def test_screenshot_verified_png_and_dimensions(tmp_path, monkeypatch):
    capture = image_capture(monkeypatch)
    target = tmp_path / "shot.png"
    result = Engine().execute(Action(T.TAKE_SCREENSHOT, str(target)))
    assert result.verification == Verification.VERIFIED
    assert result.data == {"path": str(target), "width": 48, "height": 32}
    with Image.open(target) as saved:
        saved.load()
        assert saved.format == "PNG" and saved.size == (48, 32)
    capture.assert_called_once_with(all_screens=True)
    assert sorted(item.name for item in tmp_path.iterdir()) == ["shot.png"]


@pytest.mark.parametrize("name", ["shot.jpg", "bad?.png"])
def test_screenshot_invalid_destination_rejected_before_capture(tmp_path, monkeypatch, name):
    capture = image_capture(monkeypatch)
    with pytest.raises((ValueError, PermissionError)):
        Engine().execute(Action(T.TAKE_SCREENSHOT, str(tmp_path / name)))
    capture.assert_not_called()


def test_screenshot_missing_parent_rejected_before_capture(tmp_path, monkeypatch):
    capture = image_capture(monkeypatch)
    with pytest.raises((OSError, ValueError)):
        Engine().execute(Action(T.TAKE_SCREENSHOT, str(tmp_path / "missing" / "shot.png")))
    capture.assert_not_called()


def test_screenshot_no_overwrite_even_at_publication(tmp_path, monkeypatch):
    image_capture(monkeypatch)
    target = tmp_path / "shot.png"
    target.write_bytes(b"user data")
    with pytest.raises(FileExistsError):
        desktop.screenshot(target)
    assert target.read_bytes() == b"user data"
    target.unlink()

    original_publish = desktop._publish_screenshot
    def colliding_publish(stage, destination):
        destination.write_bytes(b"late user data")
        return original_publish(stage, destination)
    monkeypatch.setattr(desktop, "_publish_screenshot", colliding_publish)
    with pytest.raises(FileExistsError):
        desktop.screenshot(target)
    assert target.read_bytes() == b"late user data"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["shot.png"]


def test_screenshot_parent_change_and_capture_failure_clean_stage(tmp_path, monkeypatch):
    image_capture(monkeypatch)
    identity = desktop._parent_identity(tmp_path)
    calls = iter([identity, (identity[0], identity[1] + 1)])
    monkeypatch.setattr(desktop, "_parent_identity", lambda _path: next(calls))
    with pytest.raises(OSError, match="parent changed"):
        desktop.screenshot(tmp_path / "shot.png")
    assert list(tmp_path.iterdir()) == []

    monkeypatch.undo()
    capture = Mock(side_effect=OSError("capture failed"))
    monkeypatch.setattr("PIL.ImageGrab.grab", capture)
    with pytest.raises(OSError, match="capture failed"):
        desktop.screenshot(tmp_path / "shot.png")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure", ["malformed", "dimensions", "publish"])
def test_screenshot_validation_or_publication_failure_cleans_stage(tmp_path, monkeypatch, failure):
    image_capture(monkeypatch)
    if failure == "malformed":
        class BadCapture:
            size = (48, 32)
            def save(self, destination, format): destination.write(b"not a PNG")
            def close(self): pass
        monkeypatch.setattr("PIL.ImageGrab.grab", lambda **_kwargs: BadCapture())
    elif failure == "dimensions":
        monkeypatch.setattr(desktop, "_virtual_desktop_size", lambda: (49, 32))
    else:
        monkeypatch.setattr(desktop, "_publish_screenshot", Mock(side_effect=OSError("publish failed")))
    with pytest.raises((OSError, ValueError, SyntaxError)):
        desktop.screenshot(tmp_path / "shot.png")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure", ["capture_permission", "capture_disk_full",
                                      "publish_permission", "publish_disk_full"])
def test_screenshot_permission_or_disk_failure_leaves_no_partial_output(tmp_path, monkeypatch, failure):
    image_capture(monkeypatch)
    target = tmp_path / "shot.png"
    error = (PermissionError(errno.EACCES, "access denied") if "permission" in failure
             else OSError(errno.ENOSPC, "disk full"))
    if failure.startswith("capture"):
        class FailedCapture:
            def save(self, output, format):
                output.write(b"partial")
                raise error
            def close(self): pass
        monkeypatch.setattr("PIL.ImageGrab.grab", lambda **_kwargs: FailedCapture())
    else:
        monkeypatch.setattr(desktop.os, "rename", Mock(side_effect=error))
    with pytest.raises((PermissionError, OSError)):
        desktop.screenshot(target)
    assert list(tmp_path.iterdir()) == []


def test_screenshot_cleanup_does_not_delete_replaced_stage(tmp_path, monkeypatch):
    image_capture(monkeypatch)
    replaced = []
    def replace_stage(stage, _destination):
        moved = tmp_path / "moved-owned-stage.png"
        stage.rename(moved)
        stage.write_bytes(b"unrelated user file")
        replaced.append(stage)
        raise OSError("publication failed")
    monkeypatch.setattr(desktop, "_publish_screenshot", replace_stage)
    with pytest.raises(OSError, match="publication failed"):
        desktop.screenshot(tmp_path / "shot.png")
    assert replaced[0].read_bytes() == b"unrelated user file"
    assert not (tmp_path / "shot.png").exists()


def test_screenshot_geometry_change_or_no_op_publication_never_succeeds(tmp_path, monkeypatch):
    image_capture(monkeypatch)
    dimensions = iter([(48, 32), (49, 32)])
    monkeypatch.setattr(desktop, "_virtual_desktop_size", lambda: next(dimensions))
    with pytest.raises(OSError, match="geometry changed"):
        desktop.screenshot(tmp_path / "shot.png")
    assert list(tmp_path.iterdir()) == []

    monkeypatch.setattr(desktop, "_virtual_desktop_size", lambda: (48, 32))
    monkeypatch.setattr(desktop, "_publish_screenshot", lambda _stage, _destination: None)
    with pytest.raises(OSError, match="Published screenshot"):
        desktop.screenshot(tmp_path / "shot.png")
    assert list(tmp_path.iterdir()) == []


def test_screenshot_confirmation_cancel_expiry_and_parent_change(tmp_path, monkeypatch):
    capture = image_capture(monkeypatch)
    now = [0.0]
    engine = Engine(permissions=PermissionEngine(timeout=1, confirm_low=True, clock=lambda: now[0]))
    target = tmp_path / "shot.png"
    def pending():
        with pytest.raises(ConfirmationRequired) as exc:
            engine.execute(Action(T.TAKE_SCREENSHOT, str(target)))
        return exc.value.pending
    request = pending()
    engine.cancel(request.token)
    with pytest.raises(PermissionDenied): engine.confirm(request.token)
    request = pending()
    now[0] = 2.0
    with pytest.raises(PermissionDenied): engine.confirm(request.token)
    now[0] = 0.0
    request = pending()
    identity = desktop._parent_identity(tmp_path)
    monkeypatch.setattr(desktop, "_parent_identity", lambda _path: (identity[0], identity[1] + 1))
    monkeypatch.setattr("aria.engine._parent_identity", lambda _path: (identity[0], identity[1] + 1))
    with pytest.raises(PermissionDenied): engine.confirm(request.token)
    capture.assert_not_called()


class FakeEndpoint:
    def __init__(self, level=.4, mute=False):
        self.level, self.muted = level, mute
        self.writes = 0
        self.fail_write = self.fail_read = False
    def GetMasterVolumeLevelScalar(self):
        if self.fail_read: raise OSError("readback failed")
        return self.level
    def SetMasterVolumeLevelScalar(self, value, _context):
        self.writes += 1
        if self.fail_write: raise OSError("write failed")
        self.level = value
    def GetMute(self):
        if self.fail_read: raise OSError("readback failed")
        return self.muted
    def SetMute(self, value, _context):
        self.writes += 1
        if self.fail_write: raise OSError("write failed")
        self.muted = value


def fake_volume(monkeypatch, endpoint=None, ids=None):
    endpoint = endpoint or FakeEndpoint()
    volume = desktop.Volume()
    values = iter(ids) if ids is not None else None
    monkeypatch.setattr(volume, "_device", lambda: (next(values) if values else "device-1", endpoint))
    return volume, endpoint


def test_volume_set_change_clamp_and_observed_state(monkeypatch):
    volume, endpoint = fake_volume(monkeypatch)
    engine = Engine(volume=volume)
    result = engine.execute(Action(T.SET_VOLUME, params={"level": 60}))
    assert result.verification == Verification.VERIFIED
    assert result.data == {"level": 60, "muted": False, "endpoint_id": "device-1"}
    assert engine.execute(Action(T.CHANGE_VOLUME, params={"delta": 100})).data["level"] == 100
    assert engine.execute(Action(T.CHANGE_VOLUME, params={"delta": -100})).data["level"] == 0
    assert endpoint.writes == 3


def test_mute_unmute_readback(monkeypatch):
    volume, _ = fake_volume(monkeypatch)
    engine = Engine(volume=volume)
    assert engine.execute(Action(T.MUTE)).data["muted"] is True
    assert engine.execute(Action(T.UNMUTE)).data["muted"] is False


@pytest.mark.parametrize("failure", ["missing", "changed", "write", "readback"])
def test_audio_failure_no_retry_or_false_success(monkeypatch, failure):
    volume, endpoint = fake_volume(monkeypatch, ids=["device-1", "device-2"] if failure == "changed" else None)
    if failure == "missing": monkeypatch.setattr(volume, "_device", Mock(side_effect=OSError("no device")))
    if failure == "write": endpoint.fail_write = True
    if failure == "readback":
        def wrote(_value, _context):
            endpoint.writes += 1
            endpoint.fail_read = True
        endpoint.SetMasterVolumeLevelScalar = wrote
    with pytest.raises(OSError):
        Engine(volume=volume).execute(Action(T.SET_VOLUME, params={"level": 55}))
    assert endpoint.writes <= 1


def test_audio_reports_actual_value_and_rejects_wrong_mute(monkeypatch):
    volume, endpoint = fake_volume(monkeypatch)
    def constrained(_value, _context): endpoint.writes += 1; endpoint.level = .54
    endpoint.SetMasterVolumeLevelScalar = constrained
    with pytest.raises(OSError, match="observed"):
        Engine(volume=volume).execute(Action(T.SET_VOLUME, params={"level": 55}))
    assert endpoint.writes == 1
    endpoint.SetMute = lambda _value, _context: None
    with pytest.raises(OSError, match="observed"):
        Engine(volume=volume).execute(Action(T.MUTE))


def test_change_read_failure_and_mute_write_failure_do_not_retry(monkeypatch):
    volume, endpoint = fake_volume(monkeypatch)
    endpoint.fail_read = True
    with pytest.raises(OSError, match="audio volume could not be read"):
        Engine(volume=volume).execute(Action(T.CHANGE_VOLUME, params={"delta": 10}))
    assert endpoint.writes == 0
    endpoint.fail_read = False
    endpoint.fail_write = True
    with pytest.raises(OSError, match="mute write failed"):
        Engine(volume=volume).execute(Action(T.MUTE))
    assert endpoint.writes == 1
