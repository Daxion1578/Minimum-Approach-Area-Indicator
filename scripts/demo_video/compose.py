"""録画（record.py）と札・構想映像をつないで 3 分の下書き動画を書く。

    python scripts/demo_video/compose.py --dir OUTDIR --concept ar-concept.mp4

OUTDIR に segments.json と rec/*.webm がある前提。title.png / closing.png が無ければ作る。
出力: maai-demo-draft.mp4（字幕入り）、maai-demo-draft-nosub.mp4、narration.srt、narration.json（語りの区切り）
1920x1080・30fps・H.264・音声なし・合計 180 秒。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FPS = 30
TITLE_SEC, CONCEPT_SEC, CLOSING_SEC = 0, 25, 15   # 語り v5: 題の札なし（図面から始める）、構想映像 25 秒、締めの札 15 秒
CLOSING_TALK = 12   # 締めの札の語りは 12 秒。最後の 3 秒は札だけ
FONT = "Noto Sans CJK JP"
MAXF = 1.5  # 録画を台本の秒数に合わせる早送りの上限。超える分は先頭からの 1.5 倍で流し、余りは最後のコマの静止で埋める


def run(cmd: list[str]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(" ".join(cmd), r.stderr[-1500:], file=sys.stderr)
        raise SystemExit(1)


HOLD = 1.2  # これより長い静止だけを 1.2 秒に縮める（短い静止は録画の通常の間なので触らない）


def freeze_spans(video: str, ss: float, length: float) -> list[tuple[float, float]]:
    """録画の ss から length 秒のうち、画面が動かない区間（0.3 秒以上）を、その切り出しの先頭を 0 とした秒で返す。"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{ss:.3f}", "-t", f"{length:.3f}", "-i", video, "-vf", f"fps={FPS},freezedetect=n=0.003:d=0.3", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    st = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", r.stderr)]
    en = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", r.stderr)]
    if len(st) > len(en):
        en.append(length)  # 最後まで止まっている
    return list(zip(st, en))


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def wrap(text: str, n: int = 28) -> list[str]:
    """句点で改行し、長い文は n 字で折り返す。"""
    out: list[str] = []
    for s in re.findall(r"[^。]+。?", text):
        s = s.strip()
        while len(s) > n:
            out.append(s[:n])
            s = s[n:]
        if s:
            out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--concept", required=True)
    ap.add_argument("--no-sub", action="store_true", help="字幕入りを作らない")
    a = ap.parse_args()
    d = Path(a.dir)
    tmp = d / "tmp"
    tmp.mkdir(exist_ok=True)
    seg = json.loads((d / "segments.json").read_text(encoding="utf-8"))
    video = seg["video"]
    segs = seg["segments"]
    for card in ("title", "closing"):
        if not (d / f"{card}.png").exists():
            run([sys.executable, str(ROOT / "scripts/ar_concept/render.py"), "--card", card, "--out", str(d / f"{card}.png")])

    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", "-crf", "18", "-preset", "medium"]
    vf0 = f"scale=1920:1080:flags=lanczos,fps={FPS}"
    parts: list[Path] = []

    # 1) 題の札（TITLE_SEC が 0 なら入れない）
    if TITLE_SEC:
        p = tmp / "p0_title.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(d / "title.png"), "-t", str(TITLE_SEC), "-vf", vf0, *enc, str(p)])
        parts.append(p)

    # 2) 録画を行ごとに切って台本の秒数に合わせる（速度を変える。足りなければ最後のコマを延ばす）
    narr: list[dict] = []
    t = 0.0
    for i, s in enumerate(segs):
        target = float(s["target_sec"])
        src_len = s["end"] - s["start"]
        ss = s["start"]
        out_len = target
        p = tmp / f"p{i + 1}_{s['id']}.mp4"
        # 動かない部分（読み込み待ちなど）を検出して、長い静止は HOLD 秒だけ残して落とす。操作の見た目の速さは変えない
        frz = freeze_spans(video, ss, src_len)
        # 台本の秒数を超えた分だけ、長い静止から順に縮める（読ませたい静止画面は、時間に余裕があれば縮めない）
        excess = src_len - target
        cap = max([e - st for st, e in frz], default=0.0) + 1.0
        if excess > 0 and frz:
            lo, hi = HOLD, cap
            if sum(max(0.0, e - st - lo) for st, e in frz) <= excess:
                cap = lo          # 縮めきっても足りない分は早送り（MAXF まで）
            else:
                for _ in range(40):
                    mid = (lo + hi) / 2
                    if sum(max(0.0, e - st - mid) for st, e in frz) > excess:
                        lo = mid
                    else:
                        hi = mid
                cap = hi
        kept = src_len - sum(max(0.0, e - st - cap) for st, e in frz)
        drops = [(st + cap, e) for st, e in frz if e - st > cap]
        factor = max(1.0, kept / target)  # >1 なら早送り（上限 MAXF。それでも超えるときだけ上限を越える）
        sel = "1" if not drops else "*".join(f"not(between(t,{a:.3f},{b:.3f}))" for a, b in drops)
        fs = tmp / f"f{i + 1}.txt"
        fs.write_text(f"fps={FPS},select='{sel}',setpts=N/({FPS}*TB),setpts=PTS/{factor:.5f},{vf0},tpad=stop_mode=clone:stop_duration={target},trim=duration={target},setpts=PTS-STARTPTS")
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ss:.3f}", "-t", f"{src_len:.3f}", "-i", video, "-vf", fs.read_text(), *enc, str(p)])
        stat = {"src": round(src_len, 2), "kept": round(kept, 2), "dropped": round(src_len - kept, 2), "factor": round(factor, 3), "after": round(kept / factor, 2), "pad": round(max(0.0, target - kept / factor), 2)}
        print(s["id"], stat)
        parts.append(p)
        # 字幕の時刻（全体の時刻）。最初の行は札の 5 秒の後ろから語る
        seg_start = TITLE_SEC + t if i == 0 else TITLE_SEC + t
        narr.append({"id": s["id"], "script": s["script"], "start": round(seg_start, 2), "end": round(seg_start + out_len, 2), "text": s["text"], "speed": round(factor, 3), "trim": stat})
        t += out_len
    rec_total = TITLE_SEC + t  # 札 + 録画（語り v4 では 0 + 120 = 2:00）

    # 3) 構想映像（CONCEPT_SEC 秒で止める）
    p = tmp / "p7_concept.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.concept, "-t", str(CONCEPT_SEC), "-vf", vf0, *enc, str(p)])
    parts.append(p)
    concept_start = rec_total
    narr.append({"id": "s6", "script": "2:20-2:45", "start": concept_start, "end": concept_start + CONCEPT_SEC,
                 "text": "この先は現地です。承認した計画をスマホでかざすと、近づけない範囲が目の前の設備に重なります。位置が決まらないときは出しません。取り違えが一番危ないからです。", "speed": 1.0})

    # 4) 締めの札（後半は無音で札を見せる）
    p = tmp / "p8_closing.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(d / "closing.png"), "-t", str(CLOSING_SEC), "-vf", vf0, *enc, str(p)])
    parts.append(p)
    c0 = concept_start + CONCEPT_SEC
    narr.append({"id": "s7", "script": "2:45-3:00", "start": c0, "end": c0 + CLOSING_TALK,
                 "text": "現場は、命を預かっています。だから、最後は人が決める。MAAI は、経験の浅い担当者の判断を助ける道具です。", "speed": 1.0})
    narr[0]["start"] = 0.0   # 最初の行は動画の頭から語る

    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{x.resolve()}'\n" for x in parts))
    nosub = d / "maai-demo-draft-nosub.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(nosub)])

    # 字幕
    cues: list[str] = []
    for k, n in enumerate(narr, 1):
        lines = wrap(n["text"])
        dur = n["end"] - n["start"]
        total_chars = sum(len(x) for x in lines)
        # 1 行ずつ、字数に比例して時間を割る（読み上げの区切りにもなる）
        cur = n["start"]
        blocks: list[tuple[float, float, str]] = []
        group: list[str] = []
        for ln in lines:
            group.append(ln)
            if len(group) == 2 or ln.endswith("。"):
                share = dur * sum(len(x) for x in group) / total_chars
                blocks.append((cur, cur + share, "\n".join(group)))
                cur += share
                group = []
        if group:
            blocks.append((cur, n["end"], "\n".join(group)))
        n["cues"] = [{"start": round(b[0], 2), "end": round(b[1], 2), "text": b[2].replace("\n", "")} for b in blocks]
        for b in blocks:
            cues.append(f"{len(cues) + 1}\n{srt_time(b[0])} --> {srt_time(min(b[1], n['end']))}\n{b[2]}\n")
    (d / "narration.srt").write_text("\n".join(cues), encoding="utf-8")
    (d / "narration.json").write_text(json.dumps(narr, ensure_ascii=False, indent=1), encoding="utf-8")

    if not a.no_sub:
        style = f"FontName={FONT},FontSize=12,PrimaryColour=&H00FFFFFF,BorderStyle=3,OutlineColour=&H00000000,BackColour=&H00000000,Outline=10,Shadow=0,Alignment=2,MarginV=36"
        srt = (d / "narration.srt").resolve().as_posix().replace(":", r"\:")   # Windows の \ はフィルタの中で特殊文字になるので / に
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(nosub), "-vf", f"subtitles='{srt}':force_style='{style}'",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", "-crf", "18", "-preset", "medium", str(d / "maai-demo-draft.mp4")])
    print("できた:", d / "maai-demo-draft.mp4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
