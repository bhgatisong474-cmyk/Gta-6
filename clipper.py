import os
import re
import subprocess
import sys

import numpy as np

URL = sys.argv[1]
N_CLIPS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
CLIP_SEC = int(sys.argv[3]) if len(sys.argv) > 3 else 30
MAX_MIN = int(sys.argv[4]) if len(sys.argv) > 4 else 120

OUT = "out"
os.makedirs(OUT, exist_ok=True)


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def get_source():
    if os.path.exists(URL):
        return URL
    src = "src.mp4"
    run([
        "yt-dlp",
        "-f", "bv*[height<=720]+ba/b[height<=720]/b",
        "--merge-output-format", "mp4",
        "--download-sections", f"*0-{MAX_MIN * 60}",
        "-o", src,
        URL,
    ])
    return src


def find_peaks(src):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
         "-f", "s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    sec = len(audio) // 16000
    if sec < CLIP_SEC + 5:
        return [0]
    rms = np.sqrt((audio[: sec * 16000].reshape(sec, 16000) ** 2).mean(axis=1))
    score = np.convolve(rms, np.ones(3) / 3, mode="same")
    score[:30] = 0
    order = np.argsort(score)[::-1]
    picked = []
    for i in order:
        if score[i] <= 0:
            break
        if all(abs(int(i) - p) >= CLIP_SEC + 10 for p in picked):
            picked.append(int(i))
        if len(picked) >= N_CLIPS:
            break
    return sorted(picked)


def transcribe(src, start, length):
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        print("faster-whisper nahi mila, captions skip:", e)
        return []
    tmp = os.path.join(OUT, "_tmp.wav")
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(length),
         "-i", src, "-vn", "-ac", "1", "-ar", "16000", tmp])
    if not hasattr(transcribe, "model"):
        transcribe.model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = transcribe.model.transcribe(tmp, word_timestamps=True, vad_filter=True)
    words = []
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip()
            if t:
                words.append((w.start, w.end, t))
    return words


def ts(t):
    t = max(0, t)
    return f"{int(t // 3600)}:{int((t % 3600) // 60):02d}:{t % 60:05.2f}"


def make_hook(words):
    if not words:
        return "WAIT FOR IT"
    text = " ".join(w[2] for w in words[:40])
    first = re.split(r"[.!?]", text)[0].split()
    hook = " ".join(first[:7]).upper()
    hook = re.sub(r"[^A-Z0-9 '?!]", "", hook)
    return hook or "WAIT FOR IT"


def write_ass(path, words, hook, length):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,78,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,420,1
Style: Hook,DejaVu Sans,84,&H0000F0FF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,8,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    parts = hook.split()
    mid = (len(parts) + 1) // 2
    hook_txt = " ".join(parts[:mid]) + "\\N" + " ".join(parts[mid:])
    lines.append(f"Dialogue: 1,{ts(0)},{ts(min(4, length))},Hook,,0,0,0,,{hook_txt}")
    for i in range(0, len(words), 3):
        grp = words[i:i + 3]
        txt = " ".join(w[2] for w in grp).upper()
        end = grp[-1][1]
        if i + 3 < len(words):
            end = max(end, min(words[i + 3][0], end + 0.4))
        lines.append(f"Dialogue: 0,{ts(grp[0][0])},{ts(end)},Cap,,0,0,0,,{txt}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")


def render(src, start, idx):
    length = CLIP_SEC
    words = transcribe(src, start, length)
    hook = make_hook(words)
    ass = os.path.join(OUT, f"clip{idx}.ass")
    write_ass(ass, words, hook, length)

    vf = (
        "[0:v]split[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=30:5[bg];"
        "[b]scale=1080:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,ass=clip{idx}.ass[v]"
    )
    out_mp4 = f"clip{idx}.mp4"
    run([
        "ffmpeg", "-v", "error", "-y",
        "-ss", str(start), "-t", str(length), "-i", os.path.abspath(src),
        "-filter_complex", vf, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-r", "30", "-pix_fmt", "yuv420p",
        out_mp4,
    ], cwd=OUT)

    with open(os.path.join(OUT, f"clip{idx}.txt"), "w", encoding="utf-8") as f:
        f.write(f"Title: {hook.title()} | GTA 6 #shorts\n")
        f.write("Hashtags: #gta6 #gta6gameplay #gta #shorts #gaming\n")
    os.remove(ass)
    print("Ready:", out_mp4, "| hook:", hook, flush=True)


def main():
    src = get_source()
    peaks = find_peaks(src)
    print("Moments (second):", peaks, flush=True)
    for i, p in enumerate(peaks, 1):
        render(src, max(0, p - int(CLIP_SEC * 0.65)), i)
    tmp = os.path.join(OUT, "_tmp.wav")
    if os.path.exists(tmp):
        os.remove(tmp)


if __name__ == "__main__":
    main()
