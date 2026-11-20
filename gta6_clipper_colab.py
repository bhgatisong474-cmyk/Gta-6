# ============ GTA 6 AUTO CLIPPER (Google Colab, FREE) ============
# Poora script ek hi Colab cell me paste karo aur Run dabao.
# 9 ghante ki stream me bhi chalta hai: pehle sirf chhota audio padhta hai,
# phir sirf best moments ke tukde download karta hai.

# ---------- SETTINGS (sirf yahan badlo) ----------
URL        = "YAHAN_YOUTUBE_LINK_PASTE_KARO"   # stream khatam ho chuki ho (VOD)
GEMINI_KEY = ""      # optional, free key: aistudio.google.com/apikey  (khali ho to random hook)
GEMINI_MODEL = "gemini-2.5-flash"   # agar error aaye to AI Studio me jo naya flash model ho wo likho
N_CLIPS    = 5       # kitne clips chahiye
LEN        = 30      # har clip kitne second ka
MODE       = "crop"  # "crop" = full zoom, "fit" = poori video beech me + blur background
LANG       = None    # None = auto, ya "hi" / "en"
# --------------------------------------------------

import os, sys, glob, subprocess, re, json, random, wave
print("Setup ho raha hai (1-2 min)...")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp[default]", "faster-whisper", "requests"], check=True)
subprocess.run("apt-get install -y -qq fonts-noto-core >/dev/null 2>&1; fc-cache -f >/dev/null 2>&1", shell=True)

import numpy as np, requests
from faster_whisper import WhisperModel

W = "/content/work"; OUT = "/content/clips"
os.makedirs(W, exist_ok=True); os.makedirs(OUT, exist_ok=True)
COOKIES = ["--cookies", "/content/cookies.txt"] if os.path.exists("/content/cookies.txt") else []

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:]); raise RuntimeError("Command fail hui")
    return r

def hms(s):
    s = int(s); return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"

# ---------- 1. chhota audio download ----------
print("1/5 Audio download (chhota, low quality)...")
for f in glob.glob(f"{W}/audio.*"): os.remove(f)
run([sys.executable, "-m", "yt_dlp", "-q", "--no-playlist", *COOKIES,
     "-f", "worstaudio/bestaudio", "-o", f"{W}/audio.%(ext)s", URL])
audio = glob.glob(f"{W}/audio.*")[0]

# ---------- 2. awaaz scan: har second ki loudness ----------
print("2/5 Sabse zordaar moments dhundh raha hu...")
SR = 4000
p = subprocess.Popen(["ffmpeg", "-v", "quiet", "-i", audio, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                     stdout=subprocess.PIPE)
rms = []; chunk = SR * 2 * 120
while True:
    b = p.stdout.read(chunk)
    if not b: break
    a = np.frombuffer(b[: len(b) // (SR * 2) * (SR * 2)], dtype=np.int16).astype(np.float32) / 32768
    if len(a): rms.extend(np.sqrt((a.reshape(-1, SR) ** 2).mean(axis=1)))
rms = np.array(rms); n = len(rms)
if n < LEN + 10: raise RuntimeError("Video bahut chhota hai")
k = 5; sm = np.convolve(rms, np.ones(k) / k, mode="same")
cs = np.cumsum(np.insert(sm, 0, 0)); R = 300
idx = np.arange(n); lo = np.clip(idx - R, 0, n); hi = np.clip(idx + R, 0, n)
base = (cs[hi] - cs[lo]) / np.maximum(hi - lo, 1)
base = np.maximum(base, np.percentile(sm, 50) + 1e-6)
score = sm / base
score[:60] = 0; score[max(0, n - LEN):] = 0
peaks = []
for i in np.argsort(-score):
    if len(peaks) >= N_CLIPS: break
    if all(abs(i - q) > LEN for q in peaks): peaks.append(int(i))
peaks.sort()
print("Moments mile:", [hms(x) for x in peaks])

# ---------- sound effects (khud banate hain, download nahi) ----------
def save_wav(path, x):
    x = np.clip(x, -1, 1); w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
    w.writeframes((x * 32767).astype(np.int16).tobytes()); w.close()
sr = 44100; t = np.arange(int(sr * .7)) / sr
noise = np.random.randn(len(t)); y = np.zeros(len(t)); prev = 0.0
for i in range(len(t)):
    a = 0.02 + 0.6 * (i / len(t)); prev += a * (noise[i] - prev); y[i] = prev
save_wav(f"{W}/whoosh.wav", y / np.abs(y).max() * np.sin(np.pi * t / .7) * .9)
t2 = np.arange(int(sr * .8)) / sr; fr = 160 * np.exp(-t2 * 4.5) + 30
save_wav(f"{W}/boom.wav", np.sin(2 * np.pi * np.cumsum(fr) / sr) * np.exp(-t2 * 4) * 1.0)

# ---------- whisper ----------
try:
    import torch; cuda = torch.cuda.is_available()
except Exception: cuda = False
model = WhisperModel("small", device="cuda" if cuda else "cpu", compute_type="float16" if cuda else "int8")

FALLBACK = ["Ye GTA 6 me kya hua?!", "Rockstar ne ye kaise kiya?", "Last tak dekho", "Ye real hai ya fake?", "Is moment ko miss mat karna"]
def make_hook(text, i):
    if GEMINI_KEY and text.strip():
        try:
            prompt = ("Ye GTA 6 gameplay clip ka transcript hai:\n" + text[:1500] +
                      "\n\nShorts ke liye likho (Hinglish, Roman script, emoji ke bina):\n"
                      "HOOK: 3 se 7 shabd ki dhamakedar hook line\nTITLE: 60 akshar se chhota catchy title\n"
                      "Sirf ye do lines do.")
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                              params={"key": GEMINI_KEY}, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            o = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            h = re.search(r"HOOK:\s*(.+)", o).group(1).strip(); tt = re.search(r"TITLE:\s*(.+)", o).group(1).strip()
            return h, tt
        except Exception as e:
            print("   (AI hook fail, random use ho raha hai):", str(e)[:80])
    h = FALLBACK[i % len(FALLBACK)]; return h, h

def ass_time(s):
    cs_ = int(round(s * 100)); return f"{cs_//360000}:{cs_//6000%60:02d}:{cs_//100%60:02d}.{cs_%100:02d}"

# ---------- 3-5. har clip: download -> captions -> hook -> render ----------
results = []
for i, pk in enumerate(peaks):
    start = max(0, min(pk - int(LEN * .6), n - LEN)); end = start + LEN
    print(f"\nClip {i+1}/{len(peaks)}  ({hms(start)} se {hms(end)})")
    print("   video tukda download...")
    for f in glob.glob(f"{W}/src{i}.*"): os.remove(f)
    run([sys.executable, "-m", "yt_dlp", "-q", "--no-playlist", *COOKIES, "--force-keyframes-at-cuts",
         "--download-sections", f"*{hms(start)}-{hms(end)}",
         "-f", "bv*[height<=720]+ba/b[height<=720]/b", "--merge-output-format", "mp4",
         "-o", f"{W}/src{i}.%(ext)s", URL])
    src = glob.glob(f"{W}/src{i}.*")[0]

    print("   captions bana raha hu...")
    segs, _ = model.transcribe(src, word_timestamps=True, language=LANG, vad_filter=True)
    words = []; full = []
    for s in segs:
        full.append(s.text)
        for w in (s.words or []): words.append((w.start, w.end, w.word.strip()))
    hook, title = make_hook(" ".join(full), i)

    ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 0", "",
           "[V4+ Styles]",
           "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
           "Style: Cap,Noto Sans,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,2,2,60,60,430,1",
           "Style: Hook,Noto Sans,100,&H004DE1FF,&H004DE1FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,8,3,8,60,60,260,1",
           "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    ass.append(f"Dialogue: 1,{ass_time(0)},{ass_time(3)},Hook,,0,0,0,,{hook.upper()}")
    for j in range(0, len(words), 3):
        g = words[j:j + 3]; txt = " ".join(x[2] for x in g).upper()
        e = g[-1][1] if j + 3 >= len(words) else words[j + 3][0]
        ass.append(f"Dialogue: 0,{ass_time(g[0][0])},{ass_time(max(e, g[0][0] + .3))},Cap,,0,0,0,,{txt}")
    open(f"{W}/sub{i}.ass", "w", encoding="utf-8").write("\n".join(ass))

    print("   hook + sound effects ke saath render...")
    boom_ms = int(max(0, (pk - start) * 1000))
    sub = f"ass={W}/sub{i}.ass"
    if MODE == "fit":
        vf = f"[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,{sub}[v]"
    else:
        vf = f"[0:v]crop=ih*9/16:ih,scale=1080:1920,{sub}[v]"
    af = f"[0:a][1:a][2:a]amix=inputs=3:duration=first,volume=3[a]"
    # [1:a]=whoosh shuru me, [2:a]=boom peak par
    fc = f"{vf};[1:a]anull[w];[2:a]adelay={boom_ms}|{boom_ms}[bm];[0:a][w][bm]amix=inputs=3:duration=first,volume=3[a]"
    outp = f"{OUT}/gta6_clip_{i+1}.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", src, "-i", f"{W}/whoosh.wav", "-i", f"{W}/boom.wav",
         "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", str(LEN),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", outp])
    results.append((outp, title))
    print("   taiyaar:", outp)

# ---------- result ----------
print("\n================ TAIYAAR ================")
for o, tt in results:
    print(f"\n{os.path.basename(o)}\n  Title: {tt} #GTA6 #Shorts\n  Description: GTA 6 gameplay clip #GTA6 #Shorts")
try:
    from google.colab import files
    for o, _ in results: files.download(o)
except Exception:
    print("\nFiles left side ke Files panel me /content/clips me hain, wahan se download karo.")
