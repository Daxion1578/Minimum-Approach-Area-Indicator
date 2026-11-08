"""本人の声（カットごとの録音）を override/<案>/pNN.wav にする。そのあと narr.py が字幕の時刻と組み立て用の音を作る。

  python take_voice.py 録音1.m4a 録音2.m4a ... [--narr]      ファイル名の p01・C1・カット1・01 などから段落（カット）の番号を読む
  python take_voice.py 声.zip [--narr]                         zip の中の音声をまとめて
  python take_voice.py p03=新規録音3.m4a C7=take2.m4a           番号を指定して入れる
  python take_voice.py a.m4a b.m4a c.m4a --in-order            渡した順に p01, p02, ...（番号が読めない名前のとき）
  オプション: --variant self（既定）／--narr（続けて python narr.py <案> を回す）／--dry（書かずに対応だけ見る）

処理: ffmpeg で 48kHz モノラル → highpass 80 Hz と弱いノイズ除去（afftdn nr=10）→ 前後の無音を詰める（頭 0.12 秒・尻 0.2 秒は残す）
→ 声の大きさ（声のある所の RMS）を段落どうしで −20 dBFS にそろえ、−3 dBFS を超える山だけ柔らかく抑える。最後の −16 LUFS は compose9.py がやる。
元のファイルは override/<案>/raw/ に写しを置く（override/ はコミットしない）。同じ番号が二つあれば新しい方を使う。
"""
from __future__ import annotations
import argparse, os, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from narr import SR, paragraphs, segments, speech_frames, runs, frame_t, pause_cues, write_wav, WIN  # noqa: E402

AUDIO = {".m4a", ".mp3", ".wav", ".aac", ".caf", ".ogg", ".opus", ".flac", ".webm", ".mp4", ".3gp", ".amr", ".wma", ".aiff", ".aif"}
TARGET_DB, KNEE = -20.0, 10 ** (-3 / 20)


def num_of(name: str) -> int | None:
    """ファイル名（拡張子なし）→ 段落の番号。読めなければ None。"""
    m = re.search(r"(?<![A-Za-z])[pPcC]\s*0*(\d{1,2})(?!\d)", name) or re.search(r"(?:カット|段落|[Cc]ut|CUT)\s*0*(\d{1,2})(?!\d)", name)
    if m:
        return int(m.group(1))
    if re.fullmatch(r"\s*0*(\d{1,2})\s*", name):
        return int(name)
    nums = re.findall(r"(?<!\d)(\d+)(?!\d)", name)
    small = [x for x in nums if len(x) <= 2]
    if len(small) == 1 and len(nums) == 1:      # 日付や時刻のような数字が混ざっていれば読まない
        return int(small[0])
    return None


def expand(items: list[str], work: Path) -> list[tuple[str | None, Path]]:
    """引数 → [(指定の番号 or None, ファイル)]。zip は音声だけを work に取り出す（名前は basename だけ使う）。"""
    out = []
    for it in items:
        tag, path = None, it
        m = re.fullmatch(r"([pPcC]\d{1,2})=(.+)", it)
        if m:
            tag, path = m.group(1), m.group(2)
        p = Path(path)
        if not p.exists():
            sys.exit(f"見つからない: {path}")
        if p.suffix.lower() == ".zip":
            d = work / f"zip-{len(out):02d}"; d.mkdir(parents=True)
            with zipfile.ZipFile(p) as z:
                for zi in z.infolist():
                    base = os.path.basename(zi.filename)
                    if zi.is_dir() or not base or base.startswith(".") or Path(base).suffix.lower() not in AUDIO or zi.file_size > 300_000_000:
                        continue
                    dst = d / base
                    with z.open(zi) as src, open(dst, "wb") as f:
                        shutil.copyfileobj(src, f)
                    t = __import__("time").mktime(zi.date_time + (0, 0, -1))
                    os.utime(dst, (t, t))
                    out.append((None, dst))
        else:
            out.append((tag, p))
    return out


def decode(p: Path) -> np.ndarray:
    af = "highpass=f=80,afftdn=nr=10:tn=1"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", str(SR), "-af", af, "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def clean(x: np.ndarray) -> tuple[np.ndarray, float]:
    """前後の無音を詰め、声の大きさをそろえる。返り値: (音, かけた dB)。"""
    m = speech_frames(x)
    sp = runs(m)
    if not sp:
        raise ValueError("声が見つからない")
    a = max(0, int((frame_t(sp[0][0]) - 0.12) * SR))
    b = min(len(x), int((frame_t(sp[-1][1]) + WIN / 2 + 0.20) * SR))
    y = x[a:b].copy()
    m2 = speech_frames(y)
    h = int(0.01 * SR)
    voiced = np.concatenate([y[i * h:i * h + int(WIN * SR)] for i in np.where(m2)[0]]) if m2.any() else y
    rms = np.sqrt(np.mean(voiced ** 2)) + 1e-9
    g_db = TARGET_DB - 20 * np.log10(rms)
    y *= 10 ** (g_db / 20)
    over = np.abs(y) > KNEE                              # −3 dBFS を超える山だけ柔らかく
    y[over] = np.sign(y[over]) * (KNEE + (1 - KNEE) * np.tanh((np.abs(y[over]) - KNEE) / (1 - KNEE)))
    fi, fo = int(0.01 * SR), int(0.03 * SR)
    y[:fi] *= np.linspace(0, 1, fi); y[-fo:] *= np.linspace(1, 0, fo)
    return y.astype(np.float32), g_db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items", nargs="+")
    ap.add_argument("--variant", default="self")
    ap.add_argument("--in-order", action="store_true")
    ap.add_argument("--narr", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    pars = paragraphs(a.variant)
    n = len(pars)
    ov = HERE / "override" / a.variant; raw = ov / "raw"
    with tempfile.TemporaryDirectory() as td:
        files = expand(a.items, Path(td))
        chosen: dict[int, Path] = {}
        unknown = []
        for i, (tag, p) in enumerate(files):
            k = int(tag[1:]) if tag else (i + 1 if a.in_order else num_of(p.stem))
            if k is None or not 1 <= k <= n:
                unknown.append(p.name); continue
            if k in chosen:
                old = chosen[k]
                keep = p if p.stat().st_mtime >= old.stat().st_mtime else old
                print(f"p{k:02d}: {old.name} と {p.name} が同じ番号 → 新しい方 {keep.name} を使う")
                chosen[k] = keep
            else:
                chosen[k] = p
        if unknown:
            print("番号が読めない（p03=ファイル名 の形で指定するか --in-order）:", ", ".join(unknown))
        if not chosen:
            sys.exit(1)
        print(f"{'段落':4} {'ファイル':28} {'長さ':>6} {'補正':>7}  字幕の切れ目")
        for k in sorted(chosen):
            p = chosen[k]
            y, g = clean(decode(p))
            segs = segments(pars[k - 1])
            pc = pause_cues(y, segs)
            mark = f"{len(segs) - 1} 個 見つかった" if pc else f"{len(segs) - 1} 個のうち足りない（文字数で按分）"
            print(f"p{k:02d}  {p.name[:28]:28} {len(y) / SR:5.1f}秒 {g:+6.1f}dB  {mark}")
            if not a.dry:
                ov.mkdir(parents=True, exist_ok=True); raw.mkdir(exist_ok=True)
                write_wav(ov / f"p{k:02d}.wav", y)
                shutil.copy2(p, raw / f"p{k:02d}{p.suffix.lower()}")
        missing = [f"p{k:02d}" for k in range(1, n + 1) if k not in chosen and not (ov / f"p{k:02d}.wav").exists()]
        if missing:
            print("まだ本人の声が無い段落（仮の読み上げのまま）:", " ".join(missing))
    if a.narr and not a.dry:
        subprocess.run([sys.executable, str(HERE / "narr.py"), a.variant], check=True)


if __name__ == "__main__":
    main()
