import numpy as np
import pytest
from aria.voice import LowConfidence, Timeline, Transcript, VoiceController, normalize

class Mic:
    def capture(self): return np.zeros(1600,dtype=np.float32)
class ASR:
    def __init__(self,confidence=.9,text="Make it 10 percent smaller."): self.confidence=confidence; self.text=text
    def transcribe(self,_): return Transcript(self.text,self.confidence,"en",.99)
class Engine:
    def __init__(self): self.actions=[]
    def execute(self,action): self.actions.append(action); return "ok"

def test_asr_normalization():
    assert normalize("Make it 10 percent smaller.")=="make it 10% smaller"
    assert normalize("Make it 1-5th of the screen.")=="make it one fifth of the screen"
    assert normalize("Make a 10% smaller.")=="make it 10% smaller"
    assert normalize("Camera kholo")=="open camera"

def test_voice_uses_existing_text_engine_and_timeline():
    engine=Engine(); ticks=iter(range(10)); voice=VoiceController(engine,Mic(),ASR(),clock=lambda:next(ticks))
    transcript,result,line=voice.run_once()
    assert engine.actions[0].params=={"scale":.9} and result=="ok"
    assert line.milliseconds()["end_to_end"]==5000

def test_low_confidence_never_executes():
    engine=Engine(); voice=VoiceController(engine,Mic(),ASR(.1))
    with pytest.raises(LowConfidence): voice.run_once()
    assert engine.actions==[]


def test_incomplete_timeline_omits_unmeasured_intervals():
    timeline = Timeline(microphone_start=1, asr_start=2)
    assert timeline.milliseconds() == {"capture": 1000}


def test_browser_timeline_intervals_are_reported():
    timeline = Timeline()
    for name, value in (
        ("browser_start", 1), ("browser_ready", 2),
        ("browser_navigation_start", 2), ("browser_navigation_complete", 2.5),
        ("browser_download_start", 3), ("browser_download_complete", 3.25),
    ):
        timeline.mark(name, value)
    values = timeline.milliseconds()
    assert values["browser_startup_ms"] == 1000
    assert values["browser_navigation_ms"] == 500
    assert values["browser_download_ms"] == 250
