import argparse, json, time
from pathlib import Path
import psutil
from faster_whisper import decode_audio
from aria.voice import LocalASR

p=argparse.ArgumentParser(); p.add_argument("audio",type=Path); p.add_argument("--model",default="base"); a=p.parse_args()
process=psutil.Process(); started=time.perf_counter(); asr=LocalASR(a.model); loaded=time.perf_counter(); audio=decode_audio(str(a.audio))
before=process.cpu_times(); warm=time.perf_counter(); result=asr.transcribe(audio); complete=time.perf_counter(); after=process.cpu_times()
print(json.dumps({"model":a.model,"transcript":result.text,"audio_seconds":round(len(audio)/16000,3),"model_load_ms":round((loaded-started)*1000,3),"transcription_ms":round((complete-warm)*1000,3),"realtime_factor":round((complete-warm)/(len(audio)/16000),3),"confidence":round(result.confidence,3),"language":result.language,"rss_mb":round(process.memory_info().rss/1048576,1),"cpu_seconds":round((after.user+after.system)-(before.user+before.system),3)},indent=2))
