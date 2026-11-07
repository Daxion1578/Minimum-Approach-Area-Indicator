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
TITLE_SEC, CONCEPT_SEC, CLOSING_SEC = 5, 27, 12
FONT = "Noto Sans CJK JP"
MAXF = 2.6  # 録画を台本の秒数に合わせる早送りの上限（ソフトウェア描画では操作ごとに約 1 秒かかり、台本より長く録れる）


def run(cmd: list[str]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(" ".join(cmd), r.stderr[-1500:], file=sys.stderr)
        raise SystemExit(1)


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

    # 1) 題の札 5 秒
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
        if i == 0:
            pass  # 最初の行は録画 15 秒 + 札 5 秒 = 台本の 20 秒
        factor = src_len / target  # >1 なら早送り
        speed_ok = 0.85 <= factor <= MAXF
        p = tmp / f"p{i + 1}_{s['id']}.mp4"
        if speed_ok:
            vf = f"setpts=PTS/{factor:.5f},{vf0},trim=duration={target},setpts=PTS-STARTPTS"
        else:  # 範囲外: 上限で速度を変え、余りは最後のコマの静止
            f = min(max(factor, 0.85), MAXF)
            vf = f"setpts=PTS/{f:.5f},{vf0},tpad=stop_mode=clone:stop_duration={target},trim=duration={target},setpts=PTS-STARTPTS"
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ss:.3f}", "-t", f"{src_len:.3f}", "-i", video, "-vf", vf, *enc, str(p)])
        parts.append(p)
        # 字幕の時刻（全体の時刻）。最初の行は札の 5 秒の後ろから語る
        seg_start = TITLE_SEC + t if i == 0 else TITLE_SEC + t
        narr.append({"id": s["id"], "script": s["script"], "start": round(seg_start, 2), "end": round(seg_start + out_len, 2), "text": s["text"], "speed": round(factor, 3)})
        t += out_len
    rec_total = TITLE_SEC + t  # 札 + 録画（= 2:21 = 141 秒）

    # 3) 構想映像（27 秒で止める）
    p = tmp / "p7_concept.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.concept, "-t", str(CONCEPT_SEC), "-vf", vf0, *enc, str(p)])
    parts.append(p)
    concept_start = rec_total
    narr.append({"id": "s7", "script": "2:21-2:48", "start": concept_start, "end": concept_start + CONCEPT_SEC,
                 "text": "この先は現地です。承認した計画をスマホでかざすと、映った機器を3Dと照らし合わせて位置を合わせ、合ったところだけに近づけない範囲を重ねます。位置が決まらないときは出しません。取り違えが一番危ないからです。充電しているかどうかはカメラで当てず、図面と開閉器の状態から計算で決めます。", "speed": 1.0})

    # 4) 締めの札 12 秒
    p = tmp / "p8_closing.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(d / "closing.png"), "-t", str(CLOSING_SEC), "-vf", vf0, *enc, str(p)])
    parts.append(p)
    c0 = concept_start + CONCEPT_SEC
    narr.append({"id": "s8", "script": "2:48-3:00", "start": c0, "end": c0 + CLOSING_SEC,
                 "text": "現場の安全を、見張りの目と経験者の頭の中だけに置きたくない。人が替わっても同じ答えにたどり着ける道具にしたくて、作りました。", "speed": 1.0})
    # 最初の行（0:00-0:20）は札の 5 秒も含めて 20 秒。語りは札から始める
    narr[0]["start"] = 0.0

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
        srt = str(d / "narration.srt").replace(":", r"\:")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(nosub), "-vf", f"subtitles='{srt}':force_style='{style}'",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", "-crf", "18", "-preset", "medium", str(d / "maai-demo-draft.mp4")])
    print("できた:", d / "maai-demo-draft.mp4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
