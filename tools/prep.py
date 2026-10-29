"""Build highlights.json (word-synced subtitle lines) from transcript.json."""
import json, re, sys

tr = json.load(open(sys.argv[1]))
out = sys.argv[2]
import wave
import numpy as np
_w = wave.open(sys.argv[3])
_sr = _w.getframerate()
_a = np.frombuffer(_w.readframes(_w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
_hop = int(_sr * 0.05)
_n = len(_a) // _hop
_db = 20 * np.log10(np.sqrt((_a[:_n * _hop].reshape(_n, _hop) ** 2).mean(1)) + 1e-6)
SP = _db > (np.percentile(_db, 35) + 6)  # True where someone is speaking


def speech_in(a, b):
    i0, i1 = int(a / 0.05), int(b / 0.05) + 1
    idx = np.nonzero(SP[i0:i1])[0]
    return (None, None) if len(idx) == 0 else ((i0 + idx[0]) * 0.05, (i0 + idx[-1] + 1) * 0.05)

# (title, start, end) -- boundaries sit on segment edges of the transcript
PICKS = [
    ("예수님이 오신다면,\n우리는 어떤 모습일까요?", 285.8, 341.7),
    ("“내 아버지의 집”", 705.2, 770.4),
    ("외형이 아니라\n마음을 갖추는 예배", 967.1, 1034.0),
    ("주의 집을 위하는 열성", 1184.5, 1252.7),
    ("웨슬리가 두려워한 것", 1366.8, 1401.4),
    ("교회의 가장 큰 위험", 1602.1, 1644.9),
    ("진짜 표적은\n십자가와 부활", 1863.9, 1916.1),
    ("참 성전이신 예수님", 2032.8, 2085.6),
    ("우리는 예배의 장인입니다", 2270.0, 2311.7),
    ("휘장이 찢어졌습니다,\n이제 누구든지 만납니다", 2388.9, 2436.5),
]

# whisper mis-hearings, fixed after reading the whole sermon
FIX = [
    ("6월절", "유월절"), ("요원복음", "요한복음"), ("복사도", "목사도"), ("보수가", "고수가"),
    ("나우스", "나오스"), ("광해에서", "광야에서"), ("의의는", "의미는"), ("부마에게", "도마에게"),
    ("복대도다", "복되도다"), ("신님이", "주님이"), ("성식만", "형식만"), ("올머스트", "올모스트"),
    ("본고로", "본 고로"), ("그렇죠? 그렇죠?", "그렇죠?"), ("환행", "관행"), ("간행", "관행"),
]


def fix(t):
    for a, b in FIX:
        t = t.replace(a, b)
    return t


MAXC = 26  # characters per subtitle event (two lines of ~13)


def wrap2(t):
    if len(t) <= 14:
        return t
    sp = [m.start() for m in re.finditer(" ", t)]
    if not sp:
        return t
    mid = len(t) / 2
    i = min(sp, key=lambda p: abs(p - mid))
    return t[:i] + "\\N" + t[i + 1:]


res = []
for n, (title, a, b) in enumerate(PICKS, 1):
    words = []
    for s in tr:
        if s["start"] >= a - 0.05 and s["end"] <= b + 0.05:
            words += s["words"]
    assert words, n
    lines, cur = [], []

    def flush():
        global cur
        if cur:
            txt = fix("".join(w["w"] for w in cur)).strip()
            lines.append(dict(s=cur[0]["s"], e=cur[-1]["e"], t=wrap2(txt)))
        cur = []

    for i, w in enumerate(words):
        cur.append(w)
        txt = "".join(x["w"] for x in cur).strip()
        gap = (words[i + 1]["s"] - w["e"]) if i + 1 < len(words) else 9
        endp = re.search(r"[.?!]$", w["w"].strip()) is not None
        if len(txt) >= MAXC or (endp and len(txt) >= 9) or gap > 0.8:
            flush()
        elif len(txt) >= 18 and re.search(r"[,]$", w["w"].strip()):
            flush()
    flush()
    # snap each line to real speech; whisper sometimes parks a first word inside a silence
    snapped = []
    carry = None
    for ln in lines:
        s0, e0 = speech_in(ln["s"] - 0.1, ln["e"] + 0.3)
        if s0 is None or (len(ln["t"].replace("\\N", "")) <= 5 and (e0 - s0) < 0.6):
            carry = ln["t"] if carry is None else carry + " " + ln["t"]
            continue
        if carry:
            ln["t"] = wrap2((carry.replace("\\N", " ") + " " + ln["t"].replace("\\N", " ")).strip())
            carry = None
        ln["s"], ln["e"] = s0, e0
        snapped.append(ln)
    lines = snapped
    for i, ln in enumerate(lines):
        e = ln["e"] + 0.15
        if i + 1 < len(lines) and lines[i + 1]["s"] - ln["e"] < 0.5:
            e = lines[i + 1]["s"] - 0.02
        ln["s"] = max(ln["s"] - 0.04, 0)
        ln["e"] = e
    res.append(dict(n=n, title=title.replace("\n", "\\N"), start=lines[0]["s"] - 0.45,
                    end=lines[-1]["e"] + 0.5, lines=lines))
json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
for h in res:
    print(f"== {h['n']:02d} {h['title']} {h['start']:.1f}-{h['end']:.1f} ({h['end']-h['start']:.0f}s)")
    for l in h["lines"]:
        print(f"  {l['s']:.2f}-{l['e']:.2f}  {l['t']}")
