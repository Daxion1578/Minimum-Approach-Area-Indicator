"""語りの原稿（scripts/<案>.txt）→ 段落ごとの音声と字幕の時刻（audio/<案>/timing.json）。

  python narr.py <案>            VOICEVOX で作る（override/<案>/pNN.wav があればそれを使う）
  python narr.py <案> --kana     読み（カナ）だけ確かめる

原稿の決まり: 空行で段落（= 1 ファイル）。<#秒#> は無音。段落の番号 pNN は上から 01, 02, ...
差し替え: override/<案>/p01.wav ... を置いて再実行すると、その段落だけ差し替わる。字幕の時刻は無音で文の切れ目を探し、
  数が足りなければ文字数で按分する。本人の録音は take_voice.py で override に入れる。
同じ文・同じ声の seg の wav は作り直さない（seg/keys.json）。今ある wav を今の原稿のものとして登録するだけなら --seed-cache。
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
    # v9: 読み上げ。override/self/pNN.wav があればそちらを使う。11/08 本人の判断: 読み上げは VOICEVOX（無料・クレジット表記が条件）。
    # 声は説明を平らに読む WhiteCUL のノーマル（抑揚を抑えめ）。商用・非商用ともクレジットで使える声から選ぶ
    # （No.7 のアナウンスは個人の非商用だけで、商用は事前の確認が要るので外した）。それまでは冥鳴ひまり（14, 話速 1.08, 抑揚 1.12）
    "self": {"speaker": 23, "speed": 1.14, "intonation": 0.9, "credit": "VOICEVOX:WhiteCUL"},   # 1.03 では語りが 173.5 秒で 3 分を超える
}
# 段落 → カット（v8 絵コンテの C1〜C10）
ACT_OF = {i: f"C{i}" for i in range(1, 11)}
SAY = [("閃絡", "せんらく"), ("3か月", "さんかげつ"), ("100トン級", "百トン級"), ("25トン級", "ニジュウゴトン級"), ("10トンを", "十トンを"), ("10トン。", "十トン。"), ("1週間", "いっしゅうかん"), ("約1万5千台", "やくいちまんごせんだい"), ("約70年", "やくななじゅうねん"), ("50代", "ごじゅうだい"), ("35件", "さんじゅうごけん"), ("15件から5件", "じゅうごけんからごけん"), ("4年間", "よねんかん"), ("相手端", "あいてたん"), ("需要家", "じゅようか"), ("3枚", "さんまい"), ("クロードコード", "クロードコード"), ("3.5トン", "さんてんごトン"), ("5.18メートル", "ゴテンイチハチメートル"), ("止めれば", "とめれば"), ("10トン級", "じゅっトン級"), ("3D", "スリーディー"), ("一つ上の", "ひとつうえの"), ("AIに", "エーアイに"), ("70トン級", "ななじゅっトン級"), ("荷重表", "かじゅうひょう"), ("元に戻す", "もとにもどす"), ("10分から30分", "じっぷんからさんじっぷん")]
SUB = [("クロードコード", "Claude Code"), ("クロード", "Claude"), ("オーケー", "OK"), ("スキル", "Skill")]


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


# ------------------------------------------------------------------ 本人の声: 無音で文の切れ目を探す（take_voice.py も使う）
HOP, WIN = 0.01, 0.03


def frame_db(x: np.ndarray) -> np.ndarray:
    """10 ms おきの 30 ms 窓の音の大きさ（dBFS）。"""
    h, w = int(HOP * SR), int(WIN * SR)
    if len(x) < w:
        return np.array([-120.0])
    c = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    idx = np.arange(0, len(x) - w + 1, h)
    return 10 * np.log10((c[idx + w] - c[idx]) / w + 1e-12)


def runs(m: np.ndarray) -> list[tuple[int, int]]:
    """bool の列 → True が続く所 [(始め, 終わり)) の一覧。"""
    d = np.diff(np.concatenate([[0], m.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0].tolist(), np.where(d == -1)[0].tolist()))


def speech_frames(x: np.ndarray) -> np.ndarray:
    """声のある窓（True）。しきい値は雑音の床と声の大きさから決める（スマホの録音の雑音に合わせる）。"""
    db = frame_db(x)
    noise, loud = np.percentile(db, 10), np.percentile(db, 97)
    m = db > max(noise + 6.0, noise + 0.3 * (loud - noise))
    for a, b in runs(m):            # 50 ms 未満の音（ぷつっという雑音）は無音
        if b - a < 5:
            m[a:b] = False
    for a, b in runs(~m):           # 60 ms 未満の無音（子音の閉じ）は声のうち
        if b - a < 6 and a > 0 and b < len(m):
            m[a:b] = True
    return m


def frame_t(i: int) -> float:
    return i * HOP + (WIN - HOP) / 2


def pause_cues(x: np.ndarray, segs: list[tuple[str, float]], min_gap: float = 0.16) -> list[tuple[float, float]] | None:
    """文ごとの（始め, 終わり）秒。文の数 − 1 個の無音（min_gap 秒以上）が、文字数から見込んだ位置の近くに見つからなければ None。"""
    m = speech_frames(x)
    sp = runs(m)
    if not sp:
        return None
    on, off = frame_t(sp[0][0]), min(len(x) / SR, frame_t(sp[-1][1]) + WIN / 2)
    k = len(segs) - 1
    if k == 0:
        return [(on, off)]
    gaps = [(frame_t(b), frame_t(a2)) for (_, b), (a2, _) in zip(sp, sp[1:]) if frame_t(a2) - frame_t(b) >= min_gap]
    if len(gaps) < k:
        return None
    w = [len(re.sub(r"[、。\s]", "", s)) + 6 * p for s, p in segs]
    tot = sum(w)
    exp = [on + (off - on) * sum(w[:j + 1]) / tot for j in range(k)]   # j 番目の文の後の切れ目の見込み
    # 見込みに近く、長い無音ほど選ぶ（短い読点の間より、文の間の長い無音を取る）。並びの順は崩さない
    cost = lambda i, j: 0.5 * abs((gaps[i][0] + gaps[i][1]) / 2 - exp[j]) - 2.0 * min(gaps[i][1] - gaps[i][0], 0.8)
    n, INF = len(gaps), float("inf")
    best = [[INF] * n for _ in range(k)]; prev = [[-1] * n for _ in range(k)]
    for i in range(n):
        best[0][i] = cost(i, 0)
    for j in range(1, k):
        run_min, run_arg = INF, -1
        for i in range(n):
            if i - 1 >= 0 and best[j - 1][i - 1] < run_min:
                run_min, run_arg = best[j - 1][i - 1], i - 1
            if run_arg >= 0:
                best[j][i] = run_min + cost(i, j); prev[j][i] = run_arg
    i = min(range(n), key=lambda q: best[k - 1][q])
    if best[k - 1][i] == INF:
        return None
    pick = [i]
    for j in range(k - 1, 0, -1):
        i = prev[j][i]; pick.append(i)
    pick.reverse()
    edges = [on] + [v for i in pick for v in gaps[i]] + [off]
    out = [(edges[2 * j], edges[2 * j + 1]) for j in range(k + 1)]
    if any(b - a < 0.3 for a, b in out):
        return None
    return out


def job_key(j: dict) -> str:
    return json.dumps([j["speaker"], j["text"], j["speed"], j["intonation"], j["pre"], j["post"]], ensure_ascii=False)


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
    # 同じ文・同じ声で作った wav があれば作り直さない（原稿を少し直したときは、変わった文だけ作る）
    kf = seg_dir / "keys.json"
    keys = json.loads(kf.read_text(encoding="utf-8")) if kf.exists() else {}
    if "--seed-cache" in sys.argv:      # 今ある seg の wav が今の原稿から作ったものだと分かっているときだけ使う
        keys.update({Path(j["out"]).stem: job_key(j) for j in jobs if Path(j["out"]).exists()})
        kf.write_text(json.dumps(keys, ensure_ascii=False, indent=0), encoding="utf-8")
        print("keys", len(keys)); return
    if not kana_only:
        jobs = [j for j in jobs if not (Path(j["out"]).exists() and keys.get(Path(j["out"]).stem) == job_key(j))]
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
        keys.update({Path(j["out"]).stem: job_key(j) for j in jobs})
        kf.write_text(json.dumps(keys, ensure_ascii=False, indent=0), encoding="utf-8")
        if kana_only:
            print((out / "kana.txt").read_text(encoding="utf-8")); return
    timing = []
    for pi, segs in enumerate(plan, 1):
        ov = HERE / "override" / variant / f"p{pi:02d}.wav"
        cues = []
        if ov.exists():
            x = trim(read_wav(ov))
            dur = len(x) / SR
            pc = pause_cues(x, segs)
            if pc:                       # 無音で文を切れた
                cues = [{"t0": round(a, 3), "t1": round(b, 3), "text": sub_text(s)} for (a, b), (s, _) in zip(pc, segs)]
            else:                        # 切れ目が数だけ見つからない: 文字数＋無音で按分
                w = [len(re.sub(r"[、。\s]", "", s)) + 6 * p for s, p in segs]
                tot, acc = sum(w), 0.0
                for (s, p), wi in zip(segs, w):
                    t0 = dur * acc / tot; acc += wi; t1 = dur * (acc - 6 * p) / tot
                    cues.append({"t0": round(t0, 3), "t1": round(t1, 3), "text": sub_text(s)})
            src = "override"
            print(f"p{pi:02d} 本人の声 {dur:.1f} 秒、字幕の時刻は" + ("無音の切れ目" if pc else "文字数の按分（切れ目が足りない）"))
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
