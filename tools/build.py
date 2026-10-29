"""Render vertical highlight clips with word-synced subtitles.

usage: build.py SRC.mp4 transcript.json highlights.json OUTDIR
highlights.json: [{"n":1,"title":"...","start":sec,"end":sec,"lines":[{"s":sec,"e":sec,"t":"자막"}]}]
Subtitle line times are absolute (source) seconds, taken from word timestamps.
"""
import json, subprocess, sys, os

src, _tr, hl_path, outdir = sys.argv[1:5]
os.makedirs(outdir, exist_ok=True)
hls = json.load(open(hl_path))
if len(sys.argv) > 5:
    only = {int(x) for x in sys.argv[5].split(",")}
    hls = [h for h in hls if h["n"] in only]

W, H = 1080, 1920
FG_H = 1215  # foreground height (crop 640x720 -> 1080x1215)
CROP_W, CROP_X = 640, 410
FONT = "NanumSquare"


def slide_ranges(s, e):
    """Ranges (relative to clip start) where the camera shows a bright full-screen slide."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{s:.2f}", "-t", f"{e-s:.2f}", "-i", src, "-vf",
                          "fps=4,scale=32:18,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = [raw[i:i + 576] for i in range(0, len(raw) - 575, 576)]
    flag = [sum(f) / len(f) > 150 for f in fr]
    out, a = [], None
    for i, x in enumerate(flag + [False]):
        if x and a is None:
            a = i / 4
        if not x and a is not None:
            out.append((a, i / 4 + 0.25)); a = None
    return out


def ts(t):
    t = max(t, 0)
    return f"{int(t//3600)}:{int(t%3600//60):02d}:{t%60:05.2f}"


for h in hls:
    n, s0, e0 = h["n"], h["start"], h["end"]
    ass = os.path.join(outdir, f"h{n:02d}.ass")
    with open(ass, "w", encoding="utf-8") as f:
        f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Sub,{FONT},66,&H00402010&,&H00000000&,&H00FFFFFF&,&H00FFFFFF&,1,0,0,0,100,100,0,0,3,18,0,5,70,70,0,1
Style: Title,{FONT},72,&H00FFFFFF&,&H00000000&,&H00502010&,&H00000000&,1,0,0,0,100,100,2,0,1,6,0,8,60,60,80,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
""")
        f.write(f"Dialogue: 0,{ts(0)},{ts(e0-s0)},Title,,0,0,0,,{h['title']}\n")
        for ln in h["lines"]:
            a, b = ln["s"] - s0, ln["e"] - s0
            # subtitle block sits in the lower bright area, vertically centered there
            f.write(f"Dialogue: 1,{ts(a)},{ts(b)},Sub,,0,0,0,,{{\\pos({W//2},{FG_H + (H-FG_H)//2 + 20})}}{ln['t']}\n")

    out = os.path.join(outdir, f"highlight_{n:02d}.mp4")
    sl = slide_ranges(s0, e0)
    on_slide = "+".join(f"between(t,{a:.2f},{z:.2f})" for a, z in sl) or "0"
    print("  slide ranges:", [(round(a, 1), round(z, 1)) for a, z in sl], flush=True)
    FIT_H = int(W * 9 / 16)
    vf = (
        f"[0:v]split=3[a][b][c];"
        # background: blurred, brightened full frame filling the canvas
        f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:8,"
        f"eq=brightness=0.18:saturation=1.1:contrast=0.95,colorlevels=rimin=0:gimin=0:bimin=0[bg];"
        # foreground: preacher crop, brightened
        f"[b]crop={CROP_W}:720:{CROP_X}:0,scale={W}:{FG_H}:flags=lanczos,"
        f"eq=brightness=0.10:contrast=1.08:saturation=1.12:gamma=1.15[fg];"
        f"[c]scale={W}:{FIT_H}:flags=lanczos,eq=brightness=0.02[fit];"
        f"[bg][fg]overlay=0:0:enable='not({on_slide})'[o1];"
        f"[o1][fit]overlay=0:{(FG_H-FIT_H)//2}:enable='{on_slide}',drawbox=x=0:y={FG_H}:w={W}:h={H-FG_H}:color=white@0.55:t=fill,"
        f"ass={ass}:fontsdir=/usr/share/fonts[v]"
    )
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-ss", f"{s0:.2f}", "-t", f"{e0-s0:.2f}", "-i", src,
        "-filter_complex", vf, "-map", "[v]", "-map", "0:a",
        "-af", "loudnorm=I=-16:TP=-1.5,afade=t=out:st=%.2f:d=0.4" % (e0 - s0 - 0.4),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out,
    ]
    print("render", n, h["title"], flush=True)
    subprocess.run(cmd, check=True)
print("ALL DONE")
