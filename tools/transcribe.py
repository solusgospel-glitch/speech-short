import json, sys, wave
import numpy as np
from faster_whisper import WhisperModel

wav, out = sys.argv[1], sys.argv[2]
w = wave.open(wav)
audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
w.close()

m = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=4)
segs, info = m.transcribe(
    audio,
    language="ko",
    word_timestamps=True,
    vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=400),
    beam_size=5,
    condition_on_previous_text=False,
    initial_prompt="한국 교회 주일예배 설교입니다. 예수님이 오신다면. 성경 말씀, 하나님, 예수 그리스도, 성령, 은혜, 십자가.",
)
res = []
for s in segs:
    res.append(dict(
        start=s.start, end=s.end, text=s.text.strip(),
        words=[dict(w=x.word, s=x.start, e=x.end, p=x.probability) for x in (s.words or [])],
    ))
    print(f"{s.end:7.1f}/{info.duration:.0f} {s.text.strip()[:40]}", flush=True)
    json.dump(res, open(out, "w"), ensure_ascii=False)
print("DONE", flush=True)
