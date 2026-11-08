"""語りの原稿（scripts/<案>.txt）→ 段落ごとの音声と字幕の時刻（audio/<案>/timing.json）。

  python narr.py <案>            VOICEVOX で作る（override/<案>/pNN.wav があればそれを使う）
  python narr.py <案> --kana     読み（カナ）だけ確かめる

原稿の決まり: 空行で段落（= 1 ファイル）。<#秒#> は無音。段落の番号 pNN は上から 01, 02, ...
差し替え: override/<案>/p01.wav ... を置いて再実行すると、その段落だけ差し替わる（字幕は文字数で按分）。
"""
from __future__ import annotations
import json, os, re, subprocess, sys, wave
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
VV = Path(os.environ.get("MAAI_VV", HERE / "vv" / "vv"))   # VOICEVOX core を動かす小さな起動スクリプト（README.md）
SR = 48000

VOICES = {
    "shizuka": {"speaker": 14, "speed": 1.03, "intonation": 1.12, "credit": "VOICEVOX:冥鳴ひまり"},
    "dan": {"speaker": 52, "speed": 0.98, "intonation": 0.85, "credit": "VOICEVOX:雀松朱司"},
    "kataru": {"speaker": 11, "speed": 1.0, "intonation": 1.15, "credit": "VOICEVOX:玄野武宏"},
    # v9: 本人の声（override/self/pNN.wav）。まだ録っていない段落は冥鳴ひまりの仮の読み上げで尺を合わせる（書き出しの表記は出さない）
    "self": {"speaker": 14, "speed": 1.03, "intonation": 1.12, "credit": ""},
}
# 段落 → カット（v8 絵コンテの C1〜C10）
ACT_OF = {i: f"C{i}" for i in range(1, 11)}
SAY = [("閃絡", "せんらく"), ("3か月", "さんかげつ"), ("100トン級", "ひゃくトンきゅう"), ("25トン級", "にじゅうごトンきゅう"), ("10トンを", "じゅっトンを"), ("相手端", "あいてたん"), ("需要家", "じゅようか"), ("3枚", "さんまい"), ("クロードコード", "クロードコード"), ("3.5トン", "さんてんごトン"), ("5.18メートル", "ゴテンイチハチメートル"), ("止めれば", "とめれば"), ("10トン級", "じゅっトン級"), ("3D", "スリーディー"), ("一つ上の", "ひとつうえの")]
SUB = [("クロードコード", "Claude Code"), ("クロード", "Claude"), ("オーケー", "OK")]


def paragraphs(variant: str) -> list[str]:
    t = (HERE / "scripts" / f"{variant}.txt").read_text(encoding="utf-8").strip()
    return [p.strip().replace("\n", "") for p in re.split(r"\n\s*\n", t) if p.strip()]


def segments(par: str) -> list[tuple[str, float]]:
    """段落 → [(文, 後ろの無音秒)]。<#x#> と 。で切る。"""
    out = []
    for chunk in re.split(r"(<#[\d.]+#>)", par):
        m = re.fullmatch(r"<#([\d.]+)#>", chunk)
        if m:
            if out:
                out[-1] = (out[-1][0], float(m.group(1)))
            continue
        for s in re.findall(r"[^。]+。?", chunk):
            s = s.strip()
            if s:
                out.append((s, 0.30 if s.endswith("。") else 0.12))
    if out:
        out[-1] = (out[-1][0], 0.0)
    return out


def say_text(s: str) -> str:
    for a, b in SAY:
        s = s.replace(a, b)
    return s


def sub_text(s: str) -> str:
    for a, b in SUB:
        s = s.replace(a, b)
    return s.rstrip("。")


def read_wav(p: Path) -> np.ndarray:
    """モノラル float32、48kHz（ffmpeg で揃える）。"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def write_wav(p: Path, x: np.ndarray) -> None:
    y = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(y.tobytes())


def trim(x: np.ndarray, thr=0.004) -> np.ndarray:
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x
    a, b = max(0, idx[0] - int(0.02 * SR)), min(len(x), idx[-1] + int(0.06 * SR))
    return x[a:b]


def main():
    variant = sys.argv[1]
    kana_only = "--kana" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = {int(x.lstrip("p")) for x in sys.argv[sys.argv.index("--only") + 1].split(",")}
    v = VOICES[variant]
    pars = paragraphs(variant)
    out = HERE / "audio" / variant
    seg_dir = out / "seg"
    seg_dir.mkdir(parents=True, exist_ok=True)
    jobs, plan = [], []
    for pi, par in enumerate(pars, 1):
        segs = segments(par)
        plan.append(segs)
        if (HERE / "override" / variant / f"p{pi:02d}.wav").exists() and not kana_only:
            continue
        if only is not None and pi not in only:
            continue
        for si, (s, _) in enumerate(segs):
            jobs.append({"speaker": v["speaker"], "text": say_text(s), "out": str(seg_dir / f"p{pi:02d}_{si:02d}.wav"),
                         "speed": v["speed"], "intonation": v["intonation"], "pre": 0.05, "post": 0.05})
    if jobs:
        jf = out / "jobs.json"
        jf.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
        res = subprocess.run([str(VV), "batch", str(jf)], capture_output=True, text=True)
        if res.returncode:
            print(res.stderr[-2000:]); sys.exit(1)
        kana = json.loads(res.stdout)
        old = {}
        if (out / "kana.txt").exists():
            for ln in (out / "kana.txt").read_text(encoding="utf-8").splitlines():
                if "\t" in ln: old[ln.split("\t")[0]] = ln.split("\t")[1]
        for k in kana: old[Path(k["out"]).stem] = k["kana"]
        (out / "kana.txt").write_text("\n".join(f"{k}\t{v}" for k, v in sorted(old.items())), encoding="utf-8")
        if kana_only:
            print((out / "kana.txt").read_text(encoding="utf-8")); return
    timing = []
    for pi, segs in enumerate(plan, 1):
        ov = HERE / "override" / variant / f"p{pi:02d}.wav"
        cues = []
        if ov.exists():
            x = trim(read_wav(ov))
            dur = len(x) / SR
            w = [len(re.sub(r"[、。\s]", "", s)) + 6 * p for s, p in segs]   # 文字数＋無音で按分
            tot, acc = sum(w), 0.0
            for (s, p), wi in zip(segs, w):
                t0 = dur * acc / tot; acc += wi; t1 = dur * (acc - 6 * p) / tot
                cues.append({"t0": round(t0, 3), "t1": round(t1, 3), "text": sub_text(s)})
            src = "override"
        else:
            parts, t = [], 0.0
            for si, (s, p) in enumerate(segs):
                sp = seg_dir / f"p{pi:02d}_{si:02d}.wav"
                x = trim(read_wav(sp if sp.exists() else sp.with_suffix(".flac")))   # リポジトリには .flac で入れてある
                cues.append({"t0": round(t, 3), "t1": round(t + len(x) / SR, 3), "text": sub_text(s)})
                parts += [x, np.zeros(int(p * SR), np.float32)]
                t += len(x) / SR + p
            x = np.concatenate(parts)
            dur = len(x) / SR
            src = "voicevox"
        write_wav(out / f"p{pi:02d}.wav", x)
        timing.append({"p": pi, "act": ACT_OF[pi], "dur": round(dur, 3), "src": src, "cues": cues})
    (out / "timing.json").write_text(json.dumps({"variant": variant, "credit": v["credit"], "paragraphs": timing}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(variant, "段落", len(timing), "語り合計 %.1f 秒" % sum(p["dur"] for p in timing))


if __name__ == "__main__":
    main()
