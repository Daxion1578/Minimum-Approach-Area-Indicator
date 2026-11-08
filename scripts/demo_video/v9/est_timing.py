"""語りの原稿（scripts/<案>.txt）から、仮の字幕の時刻（audio/<案>/timing.json）と無音の pNN.wav を作る。

VOICEVOX や本人の声がまだ無いうちに、場面の秒を決めて組み立てを始めるためのもの。読む速さは 1 秒 5.3 字（句読点を除く）で見積もる。
narr.py を回すと、timing.json と pNN.wav は本物で上書きされる。

  python est_timing.py self [--rate 5.3]
"""
from __future__ import annotations
import json, re, sys, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from narr import paragraphs, segments, sub_text, ACT_OF, VOICES, SR  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    v = sys.argv[1]
    rate = float(sys.argv[sys.argv.index("--rate") + 1]) if "--rate" in sys.argv else 5.3
    out = HERE / "audio" / v; out.mkdir(parents=True, exist_ok=True)
    timing = []
    for pi, par in enumerate(paragraphs(v), 1):
        t, cues = 0.0, []
        for s, pause in segments(par):
            n = len(re.sub(r"[、。\s]", "", s))
            d = n / rate
            cues.append({"t0": round(t, 3), "t1": round(t + d, 3), "text": sub_text(s)})
            t += d + pause
        dur = round(t, 3)
        with wave.open(str(out / f"p{pi:02d}.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(np.zeros(int(dur * SR), np.int16).tobytes())
        timing.append({"p": pi, "act": ACT_OF[pi], "dur": dur, "src": "estimate", "cues": cues})
    (out / "timing.json").write_text(json.dumps({"variant": v, "credit": VOICES.get(v, {}).get("credit", ""), "paragraphs": timing}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(v, "見積もり 語り合計 %.1f 秒" % sum(p["dur"] for p in timing), " ".join(f"{p['act']}:{p['dur']:.1f}" for p in timing))


if __name__ == "__main__":
    main()
