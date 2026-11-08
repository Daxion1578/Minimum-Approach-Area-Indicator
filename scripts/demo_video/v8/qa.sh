#!/bin/bash
# 書き出した動画の点検: 尺・形式・音量・ピーク・端の黒・2 秒おきのコマ一覧
V="$1"; O="$2"; mkdir -p "$O"
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate,sample_rate,channels -of compact "$V"
ffmpeg -hide_banner -nostats -i "$V" -af ebur128=peak=true -f null - 2>&1 | grep -E "I:|LRA:|Peak:" | tr -s ' '
ffmpeg -hide_banner -v error -i "$V" -vf "fps=1/2,scale=426:240,tile=3x4:padding=4:color=gray" "$O/sheet_%02d.png"
python3 - "$V" <<'PY'
import subprocess, sys, numpy as np
V = sys.argv[1]
d = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",V],capture_output=True,text=True).stdout)
w, h = map(int, subprocess.run(["ffprobe","-v","error","-select_streams","v","-show_entries","stream=width,height","-of","csv=p=0",V],capture_output=True,text=True).stdout.strip().split(","))
bad = []
for t in np.arange(0.5, d - 0.2, 0.5):
    b = subprocess.run(["ffmpeg","-v","error","-ss",f"{t:.2f}","-i",V,"-frames:v","1","-f","rawvideo","-pix_fmt","gray","-"],capture_output=True).stdout
    if len(b) < w * h: continue
    f = np.frombuffer(b, np.uint8).reshape(h, w)
    for name, col in (("左", f[:, :4]), ("右", f[:, -4:])):
        if col.mean() < 12: bad.append(f"{t:.1f}s {name}端が黒")
    if f.std() < 3: bad.append(f"{t:.1f}s 何も無いコマ")
print("端の黒・空のコマ:", bad[:20] if bad else "なし")
# 1 秒ごとの短時間の音量（語りのない所と効果音の跳ね）
r = subprocess.run(["ffmpeg","-hide_banner","-nostats","-i",V,"-af","ebur128","-f","null","-"],capture_output=True,text=True).stderr
import re
S = {}
for m in re.finditer(r"t:\s*([\d.]+).*?S:\s*([-\d.]+)", r):
    S[int(float(m.group(1)))] = float(m.group(2))
vals = [v for v in S.values() if v > -70]
print("短時間の音量: 最大 %.1f LUFS、中央 %.1f LUFS" % (max(vals), float(np.median(vals))))
print("跳ね（-12 LUFS より大きい秒）:", [k for k, v in S.items() if v > -12][:20])
PY
