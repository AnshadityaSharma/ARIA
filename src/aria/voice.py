from __future__ import annotations
import math, re, time
from dataclasses import dataclass
import numpy as np

class VoiceError(RuntimeError): pass
class LowConfidence(VoiceError): pass

@dataclass(frozen=True, slots=True)
class Transcript:
    text: str; confidence: float; language: str; language_probability: float

@dataclass(slots=True)
class Timeline:
    microphone_start: float=0; asr_start: float=0; transcription_complete: float=0
    command_parse: float=0; action_start: float=0; action_complete: float=0
    def milliseconds(self):
        p={"capture":(self.microphone_start,self.asr_start),"asr":(self.asr_start,self.transcription_complete),"parse":(self.transcription_complete,self.command_parse),"dispatch":(self.command_parse,self.action_start),"action":(self.action_start,self.action_complete),"end_to_end":(self.microphone_start,self.action_complete)}
        return {k:round((b-a)*1000,3) for k,(a,b) in p.items()}

class Microphone:
    def __init__(self, sample_rate=16000, max_seconds=7, silence_seconds=.7, speech_threshold=.012):
        self.sample_rate,self.max_seconds,self.silence_seconds,self.speech_threshold=sample_rate,max_seconds,silence_seconds,speech_threshold
    def capture(self):
        import sounddevice as sd
        block=int(self.sample_rate*.05); chunks=[]; speech=False; quiet=0
        with sd.InputStream(samplerate=self.sample_rate,channels=1,dtype="float32",blocksize=block) as stream:
            for _ in range(int(self.max_seconds/.05)):
                data,overflowed=stream.read(block)
                if overflowed: raise VoiceError("Microphone input overflow")
                chunks.append(data[:,0].copy()); rms=float(np.sqrt(np.mean(data*data)))
                if rms>=self.speech_threshold: speech=True; quiet=0
                elif speech: quiet+=1
                if speech and quiet*.05>=self.silence_seconds: break
        if not speech: raise VoiceError("No speech detected")
        return np.concatenate(chunks)

class LocalASR:
    def __init__(self, model="base", device="cpu", compute_type="int8"):
        from faster_whisper import WhisperModel
        self.model_name=model; self.model=WhisperModel(model,device=device,compute_type=compute_type)
    def transcribe(self,audio):
        segments,info=self.model.transcribe(audio,beam_size=1,best_of=1,vad_filter=True,vad_parameters={"min_silence_duration_ms":300},condition_on_previous_text=False)
        items=list(segments); text=" ".join(s.text.strip() for s in items).strip()
        if not text: raise VoiceError("No command was transcribed")
        avg=sum(s.avg_logprob*max(.01,s.end-s.start) for s in items)/sum(max(.01,s.end-s.start) for s in items)
        confidence=max(0.,min(1.,math.exp(avg)*float(info.language_probability)))
        return Transcript(text,confidence,info.language,float(info.language_probability))

def normalize(text):
    value=re.sub(r"[^\w%\- ]+"," ",text.casefold()).strip()
    value=re.sub(r"\bper\s*cent\b","%",value); value=re.sub(r"\b(\d+) percent\b",r"\1%",value); value=re.sub(r"\b(\d+)\s+%",r"\1%",value)
    value=re.sub(r"\b1[- ]5th\b","one fifth",value)
    value=re.sub(r"^make a (?=\d+% (?:smaller|bigger)$)","make it ",value)
    if m:=re.fullmatch(r"(.+?) (?:kholo|khol do|open karo)",value): value=f"open {m.group(1)}"
    return " ".join(value.split())

class VoiceController:
    def __init__(self,engine,microphone=None,asr=None,min_confidence=.35,clock=time.perf_counter):
        self.engine=engine; self.microphone=microphone or Microphone(); self.asr=asr or LocalASR(); self.min_confidence=min_confidence; self.clock=clock
    def run_once(self):
        from aria.parser import parse
        line=Timeline(microphone_start=self.clock()); audio=self.microphone.capture(); line.asr_start=self.clock()
        transcript=self.asr.transcribe(audio); line.transcription_complete=self.clock()
        if transcript.confidence<self.min_confidence: raise LowConfidence(f"Uncertain transcription ({transcript.confidence:.0%}): {transcript.text}")
        command=normalize(transcript.text); action=parse(command); line.command_parse=self.clock(); line.action_start=self.clock()
        result=self.engine.execute(action); line.action_complete=self.clock()
        return transcript,result,line
