"""VOICEVOX core 0.15 で文を音声にする。
python tts.py synth SPEAKER OUT.wav "文" [--speed 1.0 --pitch 0 --intonation 1.0 --pre 0.1 --post 0.1]
python tts.py kana SPEAKER "文"   # 読み（カナ）を出して確かめる
python tts.py batch JOBS.json     # [{"speaker":..,"text":..,"out":..,"speed":..}, ...]
"""
import json, sys, argparse
from pathlib import Path
from voicevox_core import VoicevoxCore, AccelerationMode

HERE = Path(__file__).resolve().parent
DIC = str(next((HERE / "vv" / "dic").glob("open_jtalk_dic_utf_8-*"), None) or next((HERE / "dic").glob("open_jtalk_dic_utf_8-*")))   # README.md の置き方
_core = None


def core(speakers):
    global _core
    if _core is None:
        _core = VoicevoxCore(acceleration_mode=AccelerationMode.CPU, open_jtalk_dict_dir=DIC, load_all_models=False, cpu_num_threads=8)
    for s in speakers:
        if not _core.is_model_loaded(s):
            _core.load_model(s)
    return _core


def query(c, text, speaker, speed=1.0, pitch=0.0, intonation=1.0, pre=0.1, post=0.15, pause=1.0):
    q = c.audio_query(text, speaker)
    q.speed_scale = speed
    q.pitch_scale = pitch
    q.intonation_scale = intonation
    q.pre_phoneme_length = pre
    q.post_phoneme_length = post
    for ap in q.accent_phrases:
        if ap.pause_mora is not None:
            ap.pause_mora.vowel_length *= pause
    return q


def kana(q):
    out = []
    for ap in q.accent_phrases:
        out.append("".join(m.text for m in ap.moras) + ("、" if ap.pause_mora is not None else ""))
    return "/".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("a", nargs="*")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--pitch", type=float, default=0.0)
    ap.add_argument("--intonation", type=float, default=1.0)
    ap.add_argument("--pre", type=float, default=0.1)
    ap.add_argument("--post", type=float, default=0.15)
    a = ap.parse_args()
    if a.cmd == "kana":
        sp, text = int(a.a[0]), a.a[1]
        c = core([sp]); print(kana(query(c, text, sp)))
    elif a.cmd == "synth":
        sp, out, text = int(a.a[0]), a.a[1], a.a[2]
        c = core([sp]); q = query(c, text, sp, a.speed, a.pitch, a.intonation, a.pre, a.post)
        Path(out).write_bytes(c.synthesis(q, sp))
    elif a.cmd == "batch":
        jobs = json.loads(Path(a.a[0]).read_text(encoding="utf-8"))
        c = core(sorted({j["speaker"] for j in jobs}))
        res = []
        for j in jobs:
            q = query(c, j["text"], j["speaker"], j.get("speed", 1.0), j.get("pitch", 0.0), j.get("intonation", 1.0), j.get("pre", 0.1), j.get("post", 0.15), j.get("pause", 1.0))
            Path(j["out"]).write_bytes(c.synthesis(q, j["speaker"]))
            res.append({"out": j["out"], "kana": kana(q)})
        print(json.dumps(res, ensure_ascii=False, indent=0))


if __name__ == "__main__":
    main()
