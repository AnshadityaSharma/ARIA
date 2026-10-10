"""Opt-in real default-speaker check using same-state writes and exact restoration."""
import os

import pytest

from aria.core import Action, ActionType as T, Verification
from aria.desktop import Volume
from aria.engine import Engine


def _restore_endpoint(endpoint, original_scalar, original_mute):
    errors = []
    for restore in (lambda: endpoint.SetMasterVolumeLevelScalar(original_scalar, None),
                    lambda: endpoint.SetMute(original_mute, None)):
        try:
            restore()
        except Exception as exc:
            errors.append(exc)
    try:
        scalar = float(endpoint.GetMasterVolumeLevelScalar())
        mute = bool(endpoint.GetMute())
    except Exception as exc:
        errors.append(exc)
    else:
        if abs(scalar - original_scalar) >= .001 or mute != original_mute:
            errors.append(AssertionError("Original speaker settings were not restored"))
    if errors:
        raise AssertionError("Original speaker settings could not be confirmed restored") from errors[0]


def test_restore_endpoint_attempts_both_settings_and_fails_if_unconfirmed():
    class Endpoint:
        def __init__(self):
            self.scalar = .4
            self.mute = True
            self.mute_restore_attempted = False
        def SetMasterVolumeLevelScalar(self, _value, _context):
            raise OSError("speaker disappeared")
        def SetMute(self, value, _context):
            self.mute_restore_attempted = True
            self.mute = value
        def GetMasterVolumeLevelScalar(self): return self.scalar
        def GetMute(self): return self.mute
    endpoint = Endpoint()
    with pytest.raises(AssertionError, match="could not be confirmed restored"):
        _restore_endpoint(endpoint, .6, False)
    assert endpoint.mute_restore_attempted


@pytest.mark.windows_integration
@pytest.mark.skipif(os.environ.get("ARIA_PHASE5_AUDIO_INTEGRATION") != "1",
                    reason="set ARIA_PHASE5_AUDIO_INTEGRATION=1 for same-state speaker writes")
def test_real_default_audio_same_state_writes_and_restore():
    volume = Volume()
    endpoint_id, endpoint = volume._device()
    original_scalar = float(endpoint.GetMasterVolumeLevelScalar())
    original_mute = bool(endpoint.GetMute())
    engine = Engine(volume=volume)
    try:
        level = round(original_scalar * 100)
        actions = [Action(T.SET_VOLUME, params={"level": level}),
                   Action(T.CHANGE_VOLUME, params={"delta": 0}),
                   Action(T.MUTE if original_mute else T.UNMUTE)]
        for action in actions:
            result = engine.execute(action)
            assert result.verification == Verification.VERIFIED
            assert result.data["endpoint_id"] == endpoint_id
            assert result.data["muted"] == original_mute
    finally:
        try:
            _restore_endpoint(endpoint, original_scalar, original_mute)
        finally:
            engine.close()
    current_id, current_endpoint = volume._device()
    assert current_id == endpoint_id
    assert abs(current_endpoint.GetMasterVolumeLevelScalar() - original_scalar) < .001
    assert bool(current_endpoint.GetMute()) == original_mute
