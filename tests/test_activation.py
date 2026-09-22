import time
from unittest.mock import Mock
import numpy as np
import pytest
from aria.activation import ActivationController, State
from aria.core import Result
from aria.engine import Engine
from aria.permissions import PermissionEngine
from aria.voice import VoiceController, Transcript


class Mic:
    def capture(self): return np.zeros(1600, dtype=np.float32)


class ASR:
    def __init__(self, text="mute"):
        self.text = text
        self.calls = 0
    def transcribe(self, _audio):
        self.calls += 1
        return Transcript(self.text, .9, "en", .99)


@pytest.mark.parametrize("answer", ["confirmed", "cancelled", "timed_out"])
def test_activation_confirmation_lifecycle(answer):
    engine = Engine(permissions=PermissionEngine(timeout=.1), shutdown=Mock())
    asr = ASR("shutdown")
    events = []
    complete = __import__("threading").Event()
    def publish(kind, payload):
        events.append((kind, payload))
        if kind == "confirmation" and answer != "timed_out":
            payload.timeline.mark("confirmation_start")
            payload.respond(answer)
        if kind == "complete": complete.set()
    controller = ActivationController(engine, VoiceController(engine, Mic(), asr), publish)
    try:
        assert controller.activate()
        assert not controller.activate()
        assert complete.wait(3)
        states = [v[0] for k,v in events if k == "state"]
        assert states[:3] == [State.LISTENING, State.PROCESSING, State.CONFIRMATION_REQUIRED]
        assert (State.SUCCESS in states) == (answer == "confirmed")
        assert engine._shutdown.call_count == (1 if answer == "confirmed" else 0)
        controller.ready()
        assert events[-1][1][0] == State.IDLE
    finally: controller.close()


def test_persistent_model_reused_and_timelines_fresh():
    engine = Engine(volume=Mock())
    asr = ASR()
    complete = __import__("threading").Event()
    controller = ActivationController(engine, VoiceController(engine, Mic(), asr),
        lambda k,v: complete.set() if k == "complete" else None)
    try:
        controller.activate(); assert complete.wait(3)
        first = controller.last_timeline
        controller.ready(); complete.clear()
        controller.activate(); assert complete.wait(3)
        second = controller.last_timeline
        assert first is not second
        assert asr.calls == 2
        assert second.events["hotkey_press"] > first.events["hotkey_press"]
        assert "confirmation_start" not in second.events
    finally: controller.close()
