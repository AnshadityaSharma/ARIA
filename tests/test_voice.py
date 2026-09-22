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
