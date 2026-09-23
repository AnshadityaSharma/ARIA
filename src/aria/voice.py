from __future__ import annotations
import math, re, time
from dataclasses import dataclass, field
import numpy as np

class VoiceError(RuntimeError): pass
class LowConfidence(VoiceError): pass

@dataclass(frozen=True, slots=True)
class Transcript:
    text: str; confidence: float; language: str; language_probability: float

@dataclass(slots=True)
class Timeline:
    microphone_start: float | None=None; asr_start: float | None=None; transcription_complete: float | None=None
    command_parse: float | None=None; action_start: float | None=None; action_complete: float | None=None
    events: dict = field(default_factory=dict)
    def mark(self, name, timestamp=None):
        value = time.perf_counter() if timestamp is None else timestamp
        self.events[name] = value
        if hasattr(self, name) and name != "events":
            setattr(self, name, value)
    def milliseconds(self):
        p={"capture":(self.microphone_start,self.asr_start),"asr":(self.asr_start,self.transcription_complete),"parse":(self.transcription_complete,self.command_parse),"dispatch":(self.command_parse,self.action_start),"action":(self.action_start,self.action_complete),"end_to_end":(self.microphone_start,self.action_complete)}
        result = {k:round((b-a)*1000,3) for k,(a,b) in p.items() if a is not None and b is not None}
        for label, start, end in (
            ("hotkey_to_listening_ms", "hotkey_press", "listening_start"),
            ("microphone_startup_ms", "microphone_requested", "microphone_ready"),
            ("hotkey_to_action_start_ms", "hotkey_press", "action_start"),
            ("hotkey_to_action_complete_ms", "hotkey_press", "action_complete"),
            ("hotkey_to_confirmation_ms", "hotkey_press", "confirmation_start"),
            ("response_to_action_start_ms", "confirmation_response", "action_start"),
            ("response_to_action_complete_ms", "confirmation_response", "action_complete"),
            ("risk_decision_ms", "parse_complete", "risk_decision"),
            ("speech_endpoint_to_asr_ms", "speech_end", "asr_start"),
            ("browser_startup_ms", "browser_start", "browser_ready"),
            ("browser_navigation_ms", "browser_navigation_start", "browser_navigation_complete"),
            ("browser_interaction_ms", "browser_interaction_start", "browser_interaction_complete"),
            ("browser_download_ms", "browser_download_start", "browser_download_complete"),
            ("youtube_result_to_playback_ms", "youtube_result_selection_start", "youtube_playback_ready"),
        ):
            if start in self.events and end in self.events:
                result[label] = round((self.events[end]-self.events[start])*1000, 3)
        return result

class Microphone:
    def __init__(self, sample_rate=16000, max_seconds=7, silence_seconds=.7, speech_threshold=.012):
        self.sample_rate,self.max_seconds,self.silence_seconds,self.speech_threshold=sample_rate,max_seconds,silence_seconds,speech_threshold
    def capture(self, on_event=None):
        import sounddevice as sd
        try:
            return self._capture(on_event)
        except sd.PortAudioError as exc:
            raise VoiceError("Microphone unavailable; check the selected input device and Windows microphone permissions") from exc

    def _capture(self, on_event=None):
        import sounddevice as sd
        event = on_event or (lambda name: None)
        event("microphone_requested")
        block=int(self.sample_rate*.05); chunks=[]; speech=False; quiet=0
        with sd.InputStream(samplerate=self.sample_rate,channels=1,dtype="float32",blocksize=block) as stream:
            event("microphone_ready")
            for _ in range(int(self.max_seconds/.05)):
                data,overflowed=stream.read(block)
                if overflowed: raise VoiceError("Microphone input overflow")
                chunks.append(data[:,0].copy()); rms=float(np.sqrt(np.mean(data*data)))
                if rms>=self.speech_threshold: speech=True; quiet=0
                elif speech: quiet+=1
                if speech and quiet*.05>=self.silence_seconds: break
        event("speech_end")
        if not speech: raise VoiceError("No speech detected")
        return np.concatenate(chunks)

class LocalASR:
    def __init__(self, model="base", device="cpu", compute_type="int8", local_files_only=True):
        from faster_whisper import WhisperModel
        self.model_name=model; self.model=WhisperModel(model,device=device,compute_type=compute_type,local_files_only=local_files_only)
    def transcribe(self,audio):
        segments,info=self.model.transcribe(audio,beam_size=1,best_of=1,vad_filter=True,vad_parameters={"min_silence_duration_ms":300},condition_on_previous_text=False)
        items=list(segments); text=" ".join(s.text.strip() for s in items).strip()
        if not text: raise VoiceError("No command was transcribed")
        avg=sum(s.avg_logprob*max(.01,s.end-s.start) for s in items)/sum(max(.01,s.end-s.start) for s in items)
        confidence=max(0.,min(1.,math.exp(avg)*float(info.language_probability)))
        return Transcript(text,confidence,info.language,float(info.language_probability))

def normalize(text):
    # File commands must keep dots, slashes, underscores, quotes and drive colons.
    if re.match(r"^(?:delete\b|(?:move|copy|rename) file\b)", text.strip(), re.I):
        return text.strip().removesuffix(".")
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
        transcript, action, line = self.prepare()
        line.action_start=self.clock()
        result=self.engine.execute(action); line.action_complete=self.clock()
        return transcript,result,line

    def prepare(self, line=None, on_state=None):
        from aria.parser import parse
        line = line or Timeline()
        state = on_state or (lambda name: None)
        state("LISTENING")
        line.microphone_start=self.clock()
        if isinstance(self.microphone, Microphone):
            audio=self.microphone.capture(on_event=lambda name: line.mark(name, self.clock()))
        else:
            audio=self.microphone.capture()
        state("PROCESSING")
        line.mark("asr_start", self.clock())
        transcript=self.asr.transcribe(audio); line.mark("transcription_complete", self.clock())
        if transcript.confidence<self.min_confidence: raise LowConfidence(f"Uncertain transcription ({transcript.confidence:.0%}): {transcript.text}")
        command=normalize(transcript.text); action=parse(command); line.mark("command_parse", self.clock())
        line.events["parse_complete"] = line.command_parse
        return transcript,action,line
