"""MAAI デモ動画 v8（実際の操作の録画が主役）を、語りの時刻に合わせて組み立てる。使い方は README.md。

  python compose8.py shizuka [--res 720|1080] [--jobs 3]     書き出し（out/maai-v8-shizuka-<res>p.mp4）
  python compose8.py shizuka --frames C1,C7                  確認用のコマ（各カット 3 か所、out/ に PNG）
  python compose8.py shizuka --at C7:3.5,C6:10                カットの中の秒を指定して PNG に

録画: assets/rec/rec8.webm（scripts/demo_video/record.py を Claude につないで撮ったもの）と s4_verdict.png（同時に撮った画面）。
点検: 24px（1280 幅基準。1080p で 36px）未満の字・画面からはみ出す字・字幕に重なる字を最後に出す。
"""
from __future__ import annotations
import argparse, json, math, re, subprocess, sys, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"     # BIZ UDPGothic / BIZ UDGothic（SIL OFL 1.1、fonts/FONTS-LICENSE.md）
FPS = 30
SR = 48000

ap = argparse.ArgumentParser()
ap.add_argument("variant")
ap.add_argument("--res", type=int, default=720)
ap.add_argument("--frames", default="")
ap.add_argument("--at", default="")
ap.add_argument("--out", default="")
ap.add_argument("--jobs", type=int, default=2)
ap.add_argument("--part", default="")
A = ap.parse_args()
V = A.variant
W, H = (1280, 720) if A.res == 720 else (1920, 1080)
K = W / 1280
SS = 2

LIGHT = (237, 243, 247)        # 明るい地（製品の場面）
PAPER = (243, 241, 236)
INK = (24, 30, 38)
SUBINK = (88, 98, 110)
RED = (214, 48, 48)
GREEN = (30, 150, 90)
BLUE = (40, 88, 160)
CYAN = (0, 150, 199)           # 製品の色（アプリの水色に合わせる）
WHITE = (255, 255, 255)

GOTH_R = str(FONTS / "BIZUDPGothic-Regular.ttf")
GOTH_B = str(FONTS / "BIZUDPGothic-Bold.ttf")
MONO = str(FONTS / "BIZUDGothic-Regular.ttf")
_fc = {}
WARN = {"small": set(), "out": set(), "cap": set()}
_frame_boxes = []


def F(path, size):
    if size < 24:
        WARN["small"].add((Path(path).stem, size))
    k = (path, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, max(8, int(round(size * K * SS))))
    return _fc[k]


def cl(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = cl(x); return 1 - (1 - x) ** 3
def smooth(x): x = cl(x); return x * x * (3 - 2 * x)
def back(x, s=1.7): x = cl(x); return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2     # 少し行き過ぎて戻る
def lerp(a, b, k): return a + (b - a) * k
def lerp4(r1, r2, k): return tuple(lerp(a, b, k) for a, b in zip(r1, r2))


# ------------------------------------------------------------------ 時刻表（絵コンテ v8 の C1〜C10）
T = json.loads((HERE / "audio" / V / "timing.json").read_text(encoding="utf-8"))
PARS = {p["act"]: p for p in T["paragraphs"]}
SPEC = {  # カット: 最小の長さ, 語りの前, 語りの後（語りの中の間は原稿の <#秒#> で取る）
    "C1": (7.0, 0.6, 0.9), "C2": (8.0, 0.4, 1.6), "C3": (7.5, 0.4, 1.9), "C4": (5.6, 0.3, 1.5),
    "C5": (11.0, 0.4, 1.6), "C6": (16.0, 0.4, 1.6), "C7": (22.0, 0.4, 2.0), "C8": (10.0, 0.4, 2.0),
    "C9": (13.0, 0.4, 1.4), "C10": (12.0, 0.6, 4.5),
}
ORDER = list(SPEC)
LIMIT = 163.0
NOFADE = {("C1", "C2"), ("C5", "C6"), ("C6", "C7"), ("C7", "C8")}   # 続けて見せる所は溶かさない


def build_timeline():
    acts, t = [], 0.0
    for a in ORDER:
        mn, lead, tail = SPEC[a]
        acts.append({"act": a, "lead": lead, "narr": PARS[a]["dur"], "tail": tail, "min": mn})
    for x in acts:
        x["dur"] = max(x["min"], x["lead"] + x["narr"] + x["tail"])
        x["start"] = t; x["n0"] = t + x["lead"]; t += x["dur"]
    return acts, t


ACTS, TOTAL = build_timeline()
ACT = {x["act"]: x for x in ACTS}


def kw(act, word, default=None, after=0):
    x = ACT[act]; cues = PARS[act]["cues"]; seen = 0
    for c in cues:
        i = c["text"].find(word)
        if i >= 0:
            if seen == after:
                return x["lead"] + c["t0"] + (c["t1"] - c["t0"]) * (i / max(1, len(c["text"])))
            seen += 1
    return default


def narr_end(act): return ACT[act]["lead"] + ACT[act]["narr"]


def cue(act, i):
    """i 番目の文が始まる・終わるカットの中の秒。"""
    c = PARS[act]["cues"][i]; L = ACT[act]["lead"]
    return L + c["t0"], L + c["t1"]


# ------------------------------------------------------------------ 描画の部品
Image.MAX_IMAGE_PIXELS = None
def new_ov(): return Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
def P(v): return v * K * SS
def flatten(base, ov): return Image.alpha_composite(base.convert("RGBA"), ov.reduce(SS)).convert("RGB")
def bg(col=LIGHT): return Image.new("RGB", (W, H), col)
def blend(a, b, k): return a if k <= 0 else (b if k >= 1 else Image.blend(a, b, k))


_rr = {}
def rounded_mask(w, h, r):
    k = (w, h, r)
    if k not in _rr:
        m = Image.new("L", (w * 2, h * 2), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], r * 2, fill=255)
        _rr[k] = m.resize((w, h), Image.LANCZOS)
    return _rr[k]


_sh = {}
def shadow(w, h, r):
    k = (w, h, r)
    if k not in _sh:
        pad = int(30 * K); s = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
        ImageDraw.Draw(s).rounded_rectangle([pad, pad + int(8 * K), pad + w, pad + h + int(8 * K)], r, fill=80)
        _sh[k] = (s.filter(ImageFilter.GaussianBlur(16 * K)), pad)
    return _sh[k]


def clamp_rect(r, im):
    x0, y0, x1, y1 = r; w, h = x1 - x0, y1 - y0
    s = min(1.0, im.width / w, im.height / h); w *= s; h *= s
    cx = cl((x0 + x1) / 2, w / 2, im.width - w / 2); cy = cl((y0 + y1) / 2, h / 2, im.height - h / 2)
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def window(frame, src, rect_src, box, radius=12, border=True, alpha=1.0, shadow_on=True):
    r = clamp_rect(rect_src, src)
    x, y, w, h = [int(round(v * K)) for v in box]
    up = w / max(1.0, r[2] - r[0]) > 1.15
    crop = src.resize((w, h), Image.LANCZOS if up else Image.BILINEAR, box=r)
    if alpha < 1:
        frame.paste(Image.blend(frame.crop((x, y, x + w, y + h)), crop, alpha), (x, y), rounded_mask(w, h, int(radius * K)))
        return r
    if shadow_on:
        sh, pad = shadow(w, h, int(radius * K)); frame.paste((150, 160, 172), (x - pad, y - pad), sh)
    frame.paste(crop, (x, y), rounded_mask(w, h, int(radius * K)))
    if border:
        ImageDraw.Draw(frame).rounded_rectangle([x, y, x + w - 1, y + h - 1], int(radius * K), outline=(196, 206, 216), width=1)
    return r


def to_screen(pt, r, box):
    x0, y0, x1, y1 = r; bx, by, bw, bh = box
    return (bx + (pt[0] - x0) / (x1 - x0) * bw, by + (pt[1] - y0) / (y1 - y0) * bh)


def fit_rect(cx, cy, w, aspect=16 / 9):
    h = w / aspect; return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _note_box(d, xy, s, font, anchor, is_cap=False):
    try:
        b = d.textbbox((P(xy[0]), P(xy[1])), s, font=font, anchor=anchor)
    except Exception:
        return
    bb = tuple(v / (K * SS) for v in b)
    if bb[0] < -1 or bb[2] > 1281 or bb[1] < -1 or bb[3] > 721:
        WARN["out"].add(s[:24])
    _frame_boxes.append((bb, is_cap, s))


def text(d, xy, s, font, fill, anchor="la", stroke=0, stroke_fill=None, alpha=1.0, is_cap=False):
    if alpha <= 0.02 or not s: return
    f = fill if len(fill) == 4 else fill + (int(255 * alpha),)
    sf = (stroke_fill or (0, 0, 0)) + (int(255 * alpha),) if stroke else None
    d.text((P(xy[0]), P(xy[1])), s, font=font, fill=f, anchor=anchor, stroke_width=int(stroke * K * SS), stroke_fill=sf)
    if alpha > 0.5:
        _note_box(d, xy, s, font, anchor, is_cap)


def seg(d, a, b, frac, col, w=3, alpha=1.0):
    if frac <= 0 or alpha <= 0: return
    e = (lerp(a[0], b[0], cl(frac)), lerp(a[1], b[1], cl(frac)))
    d.line([(P(a[0]), P(a[1])), (P(e[0]), P(e[1]))], fill=col + (int(255 * alpha),), width=int(w * K * SS))


def tag(d, xy, s, size=24, fg=WHITE, bg_=INK, alpha=1.0, anchor="ls"):
    if alpha <= 0: return
    f = F(GOTH_B, size); tw = d.textlength(s, font=f) / SS / K
    x, y = xy
    if anchor == "rs": x -= tw + 18
    if anchor == "ms": x -= (tw + 18) / 2
    d.rounded_rectangle([P(x), P(y - size - 12), P(x + tw + 18), P(y + 4)], int(8 * K * SS), fill=bg_ + (int(235 * alpha),))
    text(d, (x + 9, y - 4), s, f, fg, anchor="ls", alpha=alpha)


def card(d, x0, y0, x1, y1, alpha=1.0, fill=WHITE, outline=None, r=16, op=240):
    d.rounded_rectangle([P(x0), P(y0), P(x1), P(y1)], int(P(r)), fill=fill + (int(op * alpha),),
                        outline=(outline + (int(255 * alpha),)) if outline else None, width=int(P(2.5)) if outline else 0)


def ripple(d, pos, u, col=CYAN):
    """押した所に広がる輪（u は 0〜1）。"""
    if not 0 <= u < 1: return
    x, y = pos; rr = lerp(8, 46, ease(u))
    d.ellipse([P(x - rr), P(y - rr), P(x + rr), P(y + rr)], outline=col + (int(240 * (1 - u)),), width=int(P(4)))
    if u < 0.35:
        r2 = 10
        d.ellipse([P(x - r2), P(y - r2), P(x + r2), P(y + r2)], fill=col + (int(200 * (1 - u / 0.35)),))


def wrap_caption(s, n=22):
    if len(s) <= n: return [s]
    cut = [m.end() for m in re.finditer("、", s)]
    best = min(cut, key=lambda c: abs(c - len(s) / 2)) if cut else len(s) // 2
    return [s[:best], s[best:]]


def caption(d, act, t, dark=False, skip=()):
    """字幕は下の帯（y 636 より下）。明るい地は墨、3D の上は白に縁取り。skip の文は画面の文字が字幕を兼ねる。"""
    x = ACT[act]; lt = t - x["lead"]
    for ci, c in enumerate(PARS[act]["cues"]):
        if ci in skip: continue
        if c["t0"] - 0.05 <= lt <= c["t1"] + 0.3:
            a = min(cl((lt - c["t0"] + 0.05) / 0.15), cl((c["t1"] + 0.3 - lt) / 0.15))
            lines = wrap_caption(c["text"])
            f = F(GOTH_B, 30)
            y0 = 702 - 36 * (len(lines) - 1)
            for i, ln in enumerate(lines):
                if dark:   # 3D の上は、薄い墨の帯に白い字
                    tw = d.textlength(ln, font=f) / SS / K; yy = y0 + 36 * i
                    d.rounded_rectangle([P(640 - tw / 2 - 16), P(yy - 31), P(640 + tw / 2 + 16), P(yy + 9)], int(P(8)), fill=(16, 20, 26, int(178 * a)))
                    text(d, (640, yy), ln, f, WHITE, anchor="ms", alpha=a, is_cap=True)
                else:
                    text(d, (640, y0 + 36 * i), ln, f, INK, anchor="ms", alpha=a, is_cap=True)
            return


def chip_step(d, n, name, alpha=1.0):
    """下の帯の左に「STEP n/4 名前」。"""
    if alpha <= 0: return
    tag(d, (24, 700), f"STEP {n}/4", 24, fg=WHITE, bg_=CYAN, alpha=alpha)
    f = F(GOTH_B, 24); w = d.textlength(f"STEP {n}/4", font=f) / SS / K
    text(d, (24 + w + 30, 696), name, F(GOTH_B, 24), INK, anchor="ls", alpha=alpha)


# ------------------------------------------------------------------ 素材
R7 = HERE / "assets" / "r7"   # 合成変電所の 3D（灰・充電部・クレーン・資材置場の上）
A1G = Image.open(R7 / "a_gray.jpg").convert("RGB")
A1L = Image.open(R7 / "a_live.jpg").convert("RGB")
A1C = Image.open(R7 / "a_crane.jpg").convert("RGB")
Z8 = Image.open(R7 / "z_safe.jpg").convert("RGB")
PJ = {"rope": (941.6, 439.4), "lead": (974.2, 445.7)}
DRAWD = HERE / "assets" / "draw"   # 合成変電所から生成した図面（単線結線図・平面図と断面図）
_img = {}


def img(p):
    p = str(p)
    if p not in _img: _img[p] = Image.open(p).convert("RGB")
    return _img[p]


REC = HERE / "assets" / "rec"
RECV = REC / "rec8.webm"   # 録画の秒と場面: README.md の表、segments.json
DBG = REC
if not RECV.exists():
    sys.exit(f"録画 {RECV} がありません（51MB のため Git には入れていない）。README.md の「録画」を見て置いてください。")


class Src:
    """録画を前から順に読む。先へ大きく飛ぶときと戻るときは読み直す。"""
    FR = 25
    def __init__(self): self.p = None; self.i = None; self.frame = None
    def _open(self, idx):
        if self.p: self.p.kill()
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{idx / self.FR:.3f}", "-i", str(RECV), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                  stdout=subprocess.PIPE)
        self.i = idx - 1; self.frame = None
    def _read(self):
        b = self.p.stdout.read(1920 * 1080 * 3)
        if len(b) < 1920 * 1080 * 3: return self.frame or Image.new("RGB", (1920, 1080))
        return Image.frombytes("RGB", (1920, 1080), b)
    def get(self, ts):
        idx = max(0, int(round(ts * self.FR)))
        if self.p is None or idx < self.i or idx > self.i + 40:
            self._open(idx)
        while self.i < idx:
            self.frame = self._read(); self.i += 1
        return self.frame


SRC = Src()


def piece(segs, t):
    """segs: [(t0, t1, s0, s1)]。カットの中の秒 t → 録画の秒と速さ。"""
    for t0, t1, s0, s1 in segs:
        if t < t1 or (t0, t1, s0, s1) == segs[-1]:
            k = cl((t - t0) / max(1e-6, t1 - t0))
            return lerp(s0, s1, k), (s1 - s0) / max(1e-6, t1 - t0)
    return segs[-1][3], 0


def zoom_at(zs, t):
    """zs: [(t, rect)]。前後の 2 つをなめらかにつなぐ。"""
    if t <= zs[0][0]: return zs[0][1]
    for (t0, r0), (t1, r1) in zip(zs, zs[1:]):
        if t <= t1: return lerp4(r0, r1, smooth((t - t0) / max(1e-6, t1 - t0)))
    return zs[-1][1]


FULL = (0, 0, 1920, 1080)
def Z(x0, y0, w):           # 左上と幅から 16:9 の範囲
    return (x0, y0, x0 + w, y0 + w * 9 / 16)


REC_BOX = (90, 8, 1100, 618.75)    # 録画の窓（下端 627。字幕の帯と重ねない）


def rec_cut(act, t, D, segs, zooms, step, ripples=(), overlay=None):
    f = bg()
    ts, sp = piece(segs, t)
    fr = SRC.get(ts)
    r = window(f, fr, zoom_at(zooms, t), REC_BOX, radius=14)
    ov = new_ov(); d = ImageDraw.Draw(ov)
    if sp > 2.2:
        tag(d, (REC_BOX[0] + REC_BOX[2] - 14, REC_BOX[1] + 44), "早送り ▶▶", 24, fg=WHITE, bg_=(40, 48, 58), alpha=0.92, anchor="rs")
    for at, pt in ripples:
        q = to_screen(pt, r, REC_BOX)
        if REC_BOX[0] < q[0] < REC_BOX[0] + REC_BOX[2] and REC_BOX[1] < q[1] < REC_BOX[1] + REC_BOX[3]:
            ripple(d, q, (t - at) / 0.7)
    if overlay:
        f = overlay(f, d, t, D, r) or f
    chip_step(d, *step)
    caption(d, act, t, False)
    return flatten(f, ov)


# ------------------------------------------------------------------ C1 依頼が届く
TARGET = (930.0, 612.0)   # 取り替える遮断器（r7/a_*.png 1920x1080 の上の位置）
C1Z = (1.0, 1.035)        # C1 の寄り。C2 はここから続ける


def c1(t, D):
    z = lerp(C1Z[0], C1Z[1], t / D)
    f, bx = cam(A1G, z, (960, 540))
    ov = new_ov(); d = ImageDraw.Draw(ov)
    k1, _ = cue("C1", 1); k2, _ = cue("C1", 2)
    p = s2s(TARGET, bx)
    a = cl((t - 0.3) / 0.3)
    if a > 0:   # 取り替える遮断器に輪と札
        if t > 0.3: ripple(d, p, ((t - 0.3) % 1.4) / 1.4, col=CYAN)
        d.ellipse([P(p[0] - 9), P(p[1] - 9), P(p[0] + 9), P(p[1] + 9)], fill=CYAN + (int(255 * a),), outline=WHITE + (int(255 * a),), width=int(P(3)))
        seg(d, (p[0] + 8, p[1] - 8), (p[0] + 60, p[1] - 60), 1, CYAN, 3, alpha=a)
        tag(d, (p[0] + 62, p[1] - 56), "6T-110 遮断器", 26, fg=WHITE, bg_=CYAN, alpha=a)
    ka = 0.5; u = back((t - ka) / 0.6); a = cl((t - ka) / 0.25)
    if a > 0:   # 依頼の札（左上から滑り込む）
        x0 = lerp(-500, 56, u); y0 = 50
        card(d, x0, y0, x0 + 470, y0 + 262, a, outline=(200, 212, 224), r=18, op=246)
        tag(d, (x0 + 22, y0 + 54), "工事の依頼", 26, fg=WHITE, bg_=CYAN, alpha=a)
        text(d, (x0 + 178, y0 + 48), "明日の作業", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a)
        rows = ["6T-110 を取り替える", "新しい遮断器は 約 3.5 t", "1号変圧器は止められない", "資材は西へ 8 m に仮置き"]
        for i, s in enumerate(rows):
            ai = cl((t - ka - 0.4 - 0.15 * i) / 0.3)
            text(d, (x0 + 24, y0 + 106 + 42 * i), s, F(GOTH_B, 27), INK, anchor="ls", alpha=a * ai)
    for i, at in enumerate((k1, k2)):   # 問い 2 つ。画面の文字が字幕を兼ねる
        s = ("止めるのは、どこまで？", "クレーンは、何トン級？")[i]
        k = back((t - at) / 0.5); a = cl((t - at) / 0.2)
        if a <= 0: continue
        y = 452 + 100 * i; x0 = lerp(1300, 712, k)
        card(d, x0, y - 66, x0 + 520, y + 20, a, r=16, op=246)
        d.rounded_rectangle([P(x0), P(y - 66), P(x0 + 10), P(y + 20)], int(P(4)), fill=(RED if i == 0 else BLUE) + (int(255 * a),))
        text(d, (x0 + 34, y), s, F(GOTH_B, 42), INK, anchor="ls", alpha=a)
    caption(d, "C1", t, True, skip=(1, 2))
    return flatten(f, ov)


# ------------------------------------------------------------------ C2 見えない（変電所 → 赤 → クレーンと閃絡 → 35 件）
def cam(src, z, c):
    cw, ch = src.width / z, src.height / z
    cx = cl(c[0], cw / 2, src.width - cw / 2); cy = cl(c[1], ch / 2, src.height - ch / 2)
    bx = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    return src.resize((W, H), Image.BILINEAR, box=bx), bx


def s2s(pt, bx): return ((pt[0] - bx[0]) / (bx[2] - bx[0]) * 1280, (pt[1] - bx[1]) / (bx[3] - bx[1]) * 720)


def zap(ov, p1, p2, seed, alpha=1.0):
    rng = np.random.default_rng(seed); n = 7
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]; L = math.hypot(dx, dy) or 1; nx, ny = -dy / L, dx / L
    pts = []
    for i in range(n + 1):
        u = i / n; off = 0 if i in (0, n) else rng.uniform(-1, 1) * max(8, L * 0.32)
        pts.append((P(p1[0] + dx * u + nx * off), P(p1[1] + dy * u + ny * off)))
    pad = int(P(60)); xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, y0 = int(min(xs)) - pad, int(min(ys)) - pad; x1, y1 = int(max(xs)) + pad, int(max(ys)) + pad
    g = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0)); gd = ImageDraw.Draw(g)
    loc = [(x - x0, y - y0) for x, y in pts]; cx, cy = (x1 - x0) / 2, (y1 - y0) / 2; rr = P(26)
    gd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(170, 210, 255, int(150 * alpha)))
    gd.line(loc, fill=(150, 200, 255, int(240 * alpha)), width=int(P(16)))
    g = g.filter(ImageFilter.GaussianBlur(P(10)))
    gd = ImageDraw.Draw(g); gd.line(loc, fill=(255, 255, 255, int(255 * alpha)), width=max(2, int(P(3.6))))
    ov.alpha_composite(g, (max(0, x0), max(0, y0)), (max(0, -x0), max(0, -y0)))


def c2(t, D):
    k_red = kw("C2", "見ただけ", 0.6); k_cr = kw("C2", "電気は", 3.0); k_arc = kw("C2", "飛び移る", 4.8)
    aP = ((PJ["rope"][0] + PJ["lead"][0]) / 2, (PJ["rope"][1] + PJ["lead"][1]) / 2)
    kz = smooth((t - k_cr) / 1.4)
    z = lerp(C1Z[1] + 0.03 * cl(t / 3), 2.0, kz) - 0.5 * smooth((t - (D - 2.2)) / 1.2)
    c = (lerp(960, aP[0], kz), lerp(540, aP[1], kz))
    f, bx = cam(A1G, z, c)
    kl = smooth((t - k_red) / 0.8); kc = smooth((t - k_cr) / 0.5)
    if kl > 0: f = blend(f, cam(A1L, z, c)[0], kl)
    if kc > 0: f = blend(f, cam(A1C, z, c)[0], kc)
    ov = new_ov(); d = ImageDraw.Draw(ov)
    p1, p2 = s2s(PJ["rope"], bx), s2s(PJ["lead"], bx)
    mc = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    p1, p2 = (mc[0] + (p1[0] - mc[0]) * 2.2, mc[1] + (p1[1] - mc[1]) * 2.2), (mc[0] + (p2[0] - mc[0]) * 2.2, mc[1] + (p2[1] - mc[1]) * 2.2)
    fi = int(round(t * FPS))
    if k_arc <= t < k_arc + 1.2:
        u = (t - k_arc) / 1.2; rr = lerp(18, 110, ease(u))
        d.ellipse([P(mc[0] - rr), P(mc[1] - rr), P(mc[0] + rr), P(mc[1] + rr)], outline=(255, 236, 200, int(220 * (1 - u))), width=int(P(4)))
    if k_arc <= t < k_arc + 0.9:
        zap(ov, p1, p2, fi, 0.55 + 0.45 * ((fi * 7919) % 5) / 4)
    elif t >= k_arc + 0.9:
        g = 1 - cl((t - k_arc - 0.9) / 1.4)
        if g > 0: zap(ov, p1, p2, fi // 8, 0.35 * g)
    d = ImageDraw.Draw(ov)
    a = cl((t - k_red - 0.3) / 0.3) * (1 - cl((t - k_cr) / 0.3))
    if a > 0: tag(d, (760, 120), "電気が残る所（充電部）", 28, fg=WHITE, bg_=RED, alpha=a)
    al = cl((t - k_arc - 0.3) / 0.3)
    if al > 0: tag(d, (mc[0] - 70, mc[1] - 10), "閃絡", 28, fg=WHITE, bg_=INK, alpha=al, anchor="rs")
    k35 = D - 2.3
    if t > k35:
        a = ease((t - k35) / 0.45); x0, y0 = 800 + lerp(40, 0, a), 60
        card(d, x0, y0, x0 + 440, y0 + 150, a)
        text(d, (x0 + 22, y0 + 102), "35件", F(GOTH_B, 62), RED, anchor="ls", alpha=a)
        text(d, (x0 + 194, y0 + 58), "感電死傷の重大事故", F(GOTH_B, 26), INK, anchor="ls", alpha=a)
        text(d, (x0 + 194, y0 + 94), "令和4〜7年度", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a)
        text(d, (x0 + 194, y0 + 126), "出典: 公的資料", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a)
    caption(d, "C2", t, True)
    out = flatten(f, ov)
    if k_arc <= t < k_arc + 0.25:
        out = Image.blend(out, Image.new("RGB", (W, H), (235, 242, 255)), 0.45 * (1 - (t - k_arc) / 0.25))
    return out


# ------------------------------------------------------------------ C3 いまの決め方（3 枚の図面 → 頭の中の立体 → 本人の言葉）
_sld, _lay = img(DRAWD / "sld-1.png"), img(DRAWD / "layout-1.png")
LAY_HMM = 1683.78 / 72 * 25.4
def lay_px(x, y): return ((80 + 2.5 * x) / 25.4 * 150, (LAY_HMM - (150 + 2.5 * y)) / 25.4 * 150)
TH = [("単線結線図", _sld, fit_rect(560, 1600, 900, 340 / 210)), ("平面図", _lay, fit_rect(*lay_px(34.0, 38.9), 1300, 340 / 210)),
      ("断面図", _lay, fit_rect(3290, 2990, 820, 340 / 210))]
SHOT_V = img(DBG / "s4_verdict.png")   # 録画と同時に撮った実際の画面（クレーンと判定）


def c3(t, D):
    f = bg(PAPER); ov = new_ov(); d = ImageDraw.Draw(ov)
    k_head = kw("C3", "頭の中", 1.8)
    for i, (name, src, rr) in enumerate(TH):
        k = back((t - 0.15 * i) / 0.55)
        if k <= 0: continue
        x = 60 + i * 400; y = lerp(420, 64, k) - (28 if i == 1 else 0)
        window(f, src, rr, (x, y, 340, 210), radius=10)
        tag(d, (x + 10, y + 204), name, 26, alpha=cl((t - 0.15 * i) / 0.3))
    kb = back((t - k_head) / 0.6)
    if kb > 0:
        cx, cy = 470, 430; w_, h_ = 420 * kb, 190 * kb
        lay_ = Image.new("RGBA", ov.size, (0, 0, 0, 0)); od = ImageDraw.Draw(lay_)
        od.rounded_rectangle([P(cx - w_ / 2 - 10), P(cy - h_ / 2 - 10), P(cx + w_ / 2 + 10), P(cy + h_ / 2 + 40)], int(P(24)), fill=WHITE + (245,), outline=INK + (180,), width=int(P(2)))
        for ox, oy, r_ in ((-170, -h_ / 2 - 36, 10), (-200, -h_ / 2 - 66, 7)):
            od.ellipse([P(cx + ox - r_), P(cy + oy - r_), P(cx + ox + r_), P(cy + oy + r_)], fill=WHITE + (245,), outline=INK + (180,), width=int(P(2)))
        f = Image.alpha_composite(f.convert("RGBA"), lay_.reduce(SS)).convert("RGB")
        if w_ > 20 and h_ > 20:
            sw, sh_ = int(w_ * K), int(h_ * K)
            sub = A1C.resize((sw, sh_), Image.BILINEAR, box=clamp_rect(fit_rect(980, 380, 900, sw / sh_), A1C))
            f.paste(sub, (int((cx - w_ / 2) * K), int((cy - h_ / 2) * K)), rounded_mask(sw, sh_, int(12 * K)))
        text(d, (cx, cy + h_ / 2 + 28), "頭の中の立体", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=cl((t - k_head - 0.3) / 0.3))
    kq = back((t - (narr_end("C3") - 0.3)) / 0.5)
    if kq > 0:
        a = cl((t - (narr_end("C3") - 0.3)) / 0.25); x0 = lerp(800, 760, kq)
        card(d, x0, 360, x0 + 460, 548, a, outline=CYAN, r=16, op=250)
        text(d, (x0 + 26, 418), "「新任の私には、", F(GOTH_B, 34), INK, anchor="ls", alpha=a)
        text(d, (x0 + 26, 464), "　まだ決めきれない」", F(GOTH_B, 34), INK, anchor="ls", alpha=a)
        text(d, (x0 + 26, 518), "作った人（変電所の工事担当）", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a)
    caption(d, "C3", t, False)
    return flatten(f, ov)


# ------------------------------------------------------------------ C4 間合い（明るく切り替わる）
def c4(t, D):
    f = bg(); ov = new_ov(); d = ImageDraw.Draw(ov)
    kt, _ = cue("C4", 1)   # 「間合い」
    for i, (name, src, rr) in enumerate(TH):   # 1) 3 枚の図面が真ん中へ集まって消える
        k = smooth(t / 0.9)
        if k >= 0.97: break
        x = lerp(60 + i * 400, 560 - 80, k); y = lerp(64, 220, k); s = lerp(1.0, 0.45, k)
        window(f, src, rr, (x, y, 340 * s, 210 * s), radius=10, alpha=1 - k)
    kw_ = back((t - 0.55) / 0.6); ko = smooth((t - kt + 0.5) / 0.4)
    if kw_ > 0 and ko < 1:   # 2) 実際の画面（答えと根拠）が開く
        w = lerp(220, 700, kw_); h = w * 9 / 16; cx, cy = 560, 248 - 30 * ko
        bx_ = (cx - w / 2, cy - h / 2, w, h)
        window(f, SHOT_V, FULL, bx_, radius=14, alpha=(1 - ko) if ko > 0 else 1.0, shadow_on=ko <= 0)
        for i, (lab, l1, l2, col) in enumerate((("答え", "35t 級で 可", "", CYAN), ("根拠", "最小離隔 5.12 m", "必要 4.00 m", GREEN))):
            a = cl((t - 1.1 - 0.35 * i) / 0.3) * (1 - ko)
            if a <= 0: continue
            y0 = 70 + 136 * i; x0 = 930
            card(d, x0, y0, x0 + 310, y0 + (104 if not l2 else 140), a, outline=col, r=14, op=250)
            tag(d, (x0 + 18, y0 + 42), lab, 24, fg=WHITE, bg_=col, alpha=a)
            text(d, (x0 + 20, y0 + 88), l1, F(GOTH_B, 32), INK, anchor="ls", alpha=a)
            if l2: text(d, (x0 + 20, y0 + 124), l2, F(GOTH_R, 26), SUBINK, anchor="ls", alpha=a)
            seg(d, (x0, y0 + 36), (bx_[0] + w * 0.80, bx_[1] + h * (0.08 + 0.06 * i)), 1, col, 3, alpha=a)
    k = back((t - kt) / 0.55)
    if k > 0:
        a = cl((t - kt) / 0.2)
        fT = F(GOTH_B, int(120 * lerp(0.7, 1.0, k)) if k < 1 else 120)
        text(d, (640, 352), "間合い", fT, INK, anchor="ms", alpha=a)
        seg(d, (470, 382), (470 + 340 * ease((t - kt - 0.2) / 0.5), 382), 1, CYAN, 8)
        a2 = cl((t - kt - 0.4) / 0.4)
        text(d, (640, 430), "MAAI  Minimum Approach Area Indicator", F(GOTH_B, 28), CYAN, anchor="ms", alpha=a2)
        text(d, (640, 488), "頭の中の立体を、図面から 3D と数字に", F(GOTH_B, 32), INK, anchor="ms", alpha=cl((t - kt - 0.7) / 0.4))
    caption(d, "C4", t, False, skip=(1,))
    return flatten(f, ov)


# ------------------------------------------------------------------ C5〜C8 実際の操作（録画）
def src2t(segs, s):
    """録画の秒 s → カットの中の秒（最初に s を含む区間）。"""
    for t0, t1, s0, s1 in segs:
        if min(s0, s1) <= s <= max(s0, s1):
            return t0 + (s - s0) / max(1e-6, s1 - s0) * (t1 - t0)
    return -9


def hl_box(d, r_src, r, col, alpha=1.0, pad=6, w=4):
    """録画の中の範囲（元の画素）を、窓の上で囲む。窓からはみ出す分は窓の内側で止める。"""
    if alpha <= 0: return None
    (x0, y0), (x1, y1) = to_screen(r_src[:2], r, REC_BOX), to_screen(r_src[2:], r, REC_BOX)
    bx0, by0, bx1, by1 = REC_BOX[0], REC_BOX[1], REC_BOX[0] + REC_BOX[2], REC_BOX[1] + REC_BOX[3]
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    if x1 < bx0 or x0 > bx1 or y1 < by0 or y0 > by1: return None
    x0, y0, x1, y1 = max(x0, bx0 + 3), max(y0, by0 + 3), min(x1, bx1 - 3), min(y1, by1 - 3)
    d.rounded_rectangle([P(x0), P(y0), P(x1), P(y1)], int(P(8)), outline=col + (int(255 * alpha),), width=int(P(w)))
    return (x0, y0, x1, y1)


def inwin(alpha_t, t, t0, t1, fade=0.25):
    return min(cl((t - t0) / fade), cl((t1 - t) / fade))


AMBER = (226, 150, 20)


def plan_c5(D):
    (a0, a1), (b0, b1), (c0, c1_) = cue("C5", 0), cue("C5", 1), cue("C5", 2)
    segs = [(0, 1.4, 36.3, 37.6), (1.4, 2.9, 37.6, 77.0), (2.9, b0 + 0.2, 77.0, 79.5),
            (b0 + 0.2, c0 - 0.3, 112.0, 119.0), (c0 - 0.3, D, 127.0, 135.4)]
    zooms = [(0, FULL), (1.3, FULL), (2.7, Z(1240, 0, 680)), (b0 + 0.15, Z(1240, 0, 680)),
             (b0 + 0.2, Z(0, 300, 800)), (c0 - 0.35, Z(0, 300, 800)), (c0 - 0.3, Z(0, 630, 800)), (D, Z(0, 660, 740))]
    ripples = [(src2t(segs, 37.1), (770, 1016)), (src2t(segs, 134.8), (138, 993))]
    return segs, zooms, ripples


def over_c5(f, d, t, D, r):
    (b0, b1), (c0, c1_) = cue("C5", 1), cue("C5", 2)
    hl_box(d, (208, 474, 406, 654), r, CYAN, inwin(None, t, b0 + 0.6, c0 - 0.35))
    hl_box(d, (14, 774, 404, 946), r, AMBER, inwin(None, t, c0 + 0.1, D))
    return f


def plan_c6(D):
    (a0, a1), (b0, b1), (c0, c1_), (e0, e1) = cue("C6", 0), cue("C6", 1), cue("C6", 2), cue("C6", 3)
    segs = [(0, 1.6, 147.6, 150.2), (1.6, 2.4, 150.2, 160.8), (2.4, b0 - 0.25, 160.8, 165.3),
            (b0 - 0.25, c0 - 0.3, 514.0, 520.5), (c0 - 0.3, c0 + 1.0, 169.3, 178.2),
            (c0 + 1.0, e0 - 0.25, 205.0, 210.5), (e0 - 0.25, D, 222.5, 231.5)]
    zooms = [(0, Z(0, 140, 800)), (2.2, Z(0, 140, 800)), (3.0, Z(0, 262, 800)), (b0 - 0.3, Z(0, 262, 800)), (b0 - 0.25, Z(120, 60, 1680)), (c0 - 0.35, Z(120, 60, 1680)),
             (c0 - 0.3, FULL), (c0 + 0.95, FULL), (c0 + 1.0, Z(1220, 197, 700)), (e0 - 0.3, Z(1220, 197, 700)),
             (e0 - 0.25, Z(350, 353, 700)), (D, Z(390, 372, 620))]
    ripples = [(src2t(segs, 149.0), (98, 312)), (src2t(segs, 169.8), (106, 648)), (src2t(segs, 177.7), (1536, 410))]
    return segs, zooms, ripples


def over_c6(f, d, t, D, r):
    (b0, b1), (c0, c1_), (e0, e1) = cue("C6", 1), cue("C6", 2), cue("C6", 3)
    a = inwin(None, t, b0 + 0.5, c0 - 0.35)
    hl_box(d, (348, 333, 580, 373), r, RED, a)
    hl_box(d, (348, 708, 588, 748), r, GREEN, inwin(None, t, b0 + 1.3, c0 - 0.35))
    hl_box(d, (1464, 368, 1702, 406), r, CYAN, inwin(None, t, c0 + 1.5, e0 - 0.3))
    a = inwin(None, t, e0 + 0.1, D)
    if a > 0:   # 停電にできる区間（緑の破線）を光らせ、開く 3 つを囲む
        p0, p1 = to_screen((688, 432), r, REC_BOX), to_screen((688, 640), r, REC_BOX)
        d.line([(P(p0[0]), P(p0[1])), (P(p1[0]), P(p1[1]))], fill=GREEN + (int(110 * a),), width=int(P(16)))
        hl_box(d, (676, 440, 834, 690), r, GREEN, a)
    return f


def plan_c7(D):
    cs = [cue("C7", i) for i in range(6)]
    c1, c2, c3, c4, c5 = cs[1][0], cs[2][0], cs[3][0], cs[4][0], cs[5][0]
    segs = [(0, 1.0, 335.4, 340.0), (1.0, c1 - 0.25, 356.5, 362.0), (c1 - 0.25, c2 - 0.3, 479.5, 483.5),
            (c2 - 0.3, c3 - 0.2, 390.0, 396.5), (c3 - 0.2, c3 + 1.0, 403.5, 406.5), (c3 + 1.0, c4 - 0.25, 436.0, 442.0),
            (c4 - 0.25, c5 - 0.25, 484.0, 488.0), (c5 - 0.25, D, 463.0, 470.0)]
    VZ = Z(1280, 8, 640)
    zooms = [(0, FULL), (1.0, FULL), (1.6, VZ), (c1 - 0.3, VZ), (c1 - 0.25, Z(0, 60, 720)), (c2 - 0.35, Z(0, 60, 720)),
             (c2 - 0.3, Z(560, 260, 1100)), (c3 - 0.25, Z(560, 260, 1100)), (c3 - 0.2, Z(480, 270, 1440)), (c3 + 1.0, Z(480, 270, 1440)),
             (c3 + 1.5, VZ), (c4 - 0.3, VZ), (c4 - 0.25, Z(0, 400, 720)), (c5 - 0.3, Z(0, 400, 720)), (c5 - 0.25, FULL)]
    ripples = [(src2t(segs, 336.2), (705, 1016)), (src2t(segs, 405.0), (955, 1016))]
    return segs, zooms, ripples


def over_c7(f, d, t, D, r):
    cs = [cue("C7", i) for i in range(6)]
    c1, c2, c4, c5 = cs[1][0], cs[2][0], cs[4][0], cs[5][0]
    a = inwin(None, t, 1.1, c1 - 0.3)
    if a > 0:   # 左に大きな数字: 3.5 t を吊る → 35t 級
        card(d, 110, 40, 470, 296, a, op=236)
        k1 = cl((t - 1.1) / 0.3); k2 = back((t - cs[0][0] - 1.6) / 0.5)
        text(d, (134, 92), "吊る機器", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a * k1)
        text(d, (134, 150), "3.5 t", F(GOTH_B, 52), INK, anchor="ls", alpha=a * k1)
        if k2 > 0:
            text(d, (134, 202), "要るクレーン", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a * cl(k2))
            text(d, (134 + lerp(20, 0, k2), 272), "35t 級", F(GOTH_B, 64), CYAN, anchor="ls", alpha=a * cl(k2))
    a = inwin(None, t, c1 + 0.2, c2 - 0.35)
    if a > 0:   # 一つ下の級が使えない理由
        hl_box(d, (24, 256, 408, 296), r, RED, a)
        x0, y0 = 770, 120
        card(d, x0, y0, x0 + 400, y0 + 250, a, outline=RED, r=16, op=246)
        text(d, (x0 + 24, y0 + 60), "10t 級", F(GOTH_B, 44), INK, anchor="ls", alpha=a)
        text(d, (x0 + 24, y0 + 104), "届くが、充電部に", F(GOTH_R, 26), SUBINK, anchor="ls", alpha=a)
        text(d, (x0 + 24, y0 + 168), "2.63 m", F(GOTH_B, 54), RED, anchor="ls", alpha=a)
        nw = d.textlength("2.63 m", font=F(GOTH_B, 54)) / SS / K
        text(d, (x0 + 24 + nw + 12, y0 + 166), "まで近づく", F(GOTH_R, 26), INK, anchor="ls", alpha=a)
        text(d, (x0 + 24, y0 + 222), "必要は 4.00 m", F(GOTH_B, 28), INK, anchor="ls", alpha=a)
        if t > c1 + 1.6:
            fw = d.textlength("10t 級", font=F(GOTH_B, 44)) / SS / K
            seg(d, (x0 + 20, y0 + 46), (x0 + 28 + fw, y0 + 46), ease((t - c1 - 1.6) / 0.35), RED, 5, alpha=a)
    hl_box(d, (12, 514, 408, 610), r, AMBER, inwin(None, t, c4 + 0.3, c5 - 0.3))
    return f


def plan_c8(D):
    (a0, a1), (b0, b1), (c0, c1_) = cue("C8", 0), cue("C8", 1), cue("C8", 2)
    segs = [(0, 1.6, 529.0, 531.4), (1.6, b0 - 0.25, 531.6, 534.2), (b0 - 0.25, b0 + 1.8, 548.6, 551.0), (b0 + 1.8, D, 553.0, 562.0)]
    zooms = [(0, FULL), (1.55, FULL), (2.1, Z(1240, 0, 680)), (b0 - 0.3, Z(1240, 0, 680)), (b0 - 0.25, FULL)]
    ripples = [(1.45, (1797, 1036))]
    return segs, zooms, ripples


def over_c8(f, d, t, D, r):
    kd, _ = cue("C8", 2)
    k = back((t - kd) / 0.5)
    if k > 0:
        a = cl((t - kd) / 0.2)
        cx, cy = 1040, 110
        rr = 50 * lerp(0.6, 1.0, k)
        d.ellipse([P(cx - rr), P(cy - rr), P(cx + rr), P(cy + rr)], fill=GREEN + (int(240 * a),))
        d.line([(P(cx - 22), P(cy + 2)), (P(cx - 6), P(cy + 18)), (P(cx + 24), P(cy - 16))], fill=(255, 255, 255, int(255 * a)), width=int(P(9)), joint="curve")
        tag(d, (cx - 84, cy + 88), "4 つとも 完了", 26, fg=WHITE, bg_=GREEN, alpha=a)
    return f


PLANS = {}


def rec_scene(act, step, plan, overlay=None):
    def fn(t, D):
        if act not in PLANS: PLANS[act] = plan(D)
        segs, zooms, ripples = PLANS[act]
        return rec_cut(act, t, D, segs, zooms, step, ripples, overlay)
    return fn


# ------------------------------------------------------------------ C9 安心の仕組みと作り方（開発の実物）
DEC8 = [("11/02", "作品名を MAAI（間合い）に決めた"), ("11/03", "離隔表は「要確認」の印つきで置く"),
        ("11/04", "テストは常にオフラインで回す"), ("11/05", "離隔の既定値を公開資料と照合"),
        ("11/06", "変圧器の取り替えは専用ベイまで止める"), ("11/07", "Claude に送る文のマスクを広げた"),
        ("11/08", "画面を「3D を全面に」作り直した")]
CC8 = [("「朝」と話す", "外の目の批評 → 残りの整理 → 今日の一つ", CYAN),
       ("「終わり」と話す", "テスト → 公開前の点検 → 判断を記録 → 報告", BLUE),
       ("係を分けた", "点検係は Sonnet、タスク係は Haiku", GREEN)]


def fit_text(d, s, font, maxw):
    """幅に収まらなければ末尾を「…」にする（はみ出しを出さない）。"""
    if d.textlength(s, font=font) / SS / K <= maxw: return s
    while s and d.textlength(s + "…", font=font) / SS / K > maxw: s = s[:-1]
    return s + "…"


def c9(t, D):
    f = bg(); ov = new_ov(); d = ImageDraw.Draw(ov)
    (a0_, a1_), (b0, b1), (c0, c1_), (e0, e1) = [cue("C9", i) for i in range(4)]
    a0 = 1 - cl((t - b0 + 0.25) / 0.35)
    if a0 > 0:   # 判定は計算、承認は人
        for i, (lab, who, col) in enumerate((("読む", "Claude", BLUE), ("決める", "計算", INK), ("承認", "人", GREEN))):
            k = back((t - 0.05 - 0.3 * i) / 0.45)
            if k <= 0: continue
            x = 170 + i * 330; y = lerp(240, 210, k)
            card(d, x, y, x + 280, y + 190, a0 * cl(k), outline=col, r=20)
            tag(d, (x + 24, y + 52), lab, 26, fg=WHITE, bg_=col, alpha=a0 * cl(k))
            text(d, (x + 140, y + 142), who, F(GOTH_B, 52), col, anchor="ms", alpha=a0 * cl(k))
            if i < 2: text(d, (x + 305, y + 108), "→", F(GOTH_B, 40), SUBINK, anchor="ms", alpha=a0 * cl(k))
        a = cl((t - 1.3) / 0.3) * a0
        text(d, (640, 500), "Claude の案も、計算で確かめてから出す", F(GOTH_B, 28), SUBINK, anchor="ms", alpha=a)
    b = cl((t - b0) / 0.35)
    if b <= 0:
        caption(d, "C9", t, False); return flatten(f, ov)
    # 左: Claude Code と、覚えたコマンド 0
    text(d, (60, 96), "Claude Code", F(GOTH_B, 46), INK, anchor="ls", alpha=b)
    text(d, (62, 136), "で作った（11/02〜11/08）", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=b)
    a2 = cl((t - c0) / 0.3)
    if a2 > 0:
        text(d, (60, 214), "覚えたコマンド", F(GOTH_B, 30), INK, anchor="ls", alpha=a2)
        text(d, (52, 392), "0", F(GOTH_B, int(round(170 * lerp(1.2, 1.0, ease((t - c0) / 0.4))))), CYAN, anchor="ls", alpha=a2)
        text(d, (196, 330), "言葉で", F(GOTH_B, 30), INK, anchor="ls", alpha=a2)
        text(d, (196, 372), "頼むだけ", F(GOTH_B, 30), INK, anchor="ls", alpha=a2)
    a3 = cl((t - e0 - 0.4) / 0.3)
    if a3 > 0:
        text(d, (60, 470), "テスト 91 件", F(GOTH_B, 30), INK, anchor="ls", alpha=a3)
        text(d, (60, 508), "push のたびに通しの確認", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a3)
    # 右: 手順と係（開発は〜コマンドは） → 判断の記録（決めたことを〜）
    out = smooth((t - e0 + 0.35) / 0.4)
    for i, (lab, flow, col) in enumerate(CC8):
        k = back((t - b0 - 0.25 - 0.3 * i) / 0.45); a = cl(k) * (1 - out)
        if a <= 0: continue
        x0 = 590 + lerp(60, 0, k) + 80 * out; y0 = 56 + 176 * i
        card(d, x0, y0, x0 + 640, y0 + 150, a, outline=col, r=16)
        text(d, (x0 + 26, y0 + 56), lab, F(GOTH_B, 32), col, anchor="ls", alpha=a)
        text(d, (x0 + 26, y0 + 108), fit_text(d, flow, F(GOTH_R, 26), 590), F(GOTH_R, 26), INK, anchor="ls", alpha=a)
    k = back((t - e0 + 0.1) / 0.5); a = cl((t - e0 + 0.1) / 0.25)
    if a > 0:
        x0 = 590 + lerp(80, 0, k); y0 = 40
        card(d, x0, y0, x0 + 640, y0 + 560, a, outline=(200, 212, 224), r=16, op=250)
        text(d, (x0 + 26, y0 + 50), "docs/decisions.md", F(MONO, 26), BLUE, anchor="ls", alpha=a)
        text(d, (x0 + 290, y0 + 50), "判断の記録", F(GOTH_B, 26), INK, anchor="ls", alpha=a)
        for i, (dt, s) in enumerate(DEC8):
            ai = cl((t - e0 - 0.1 - 0.12 * i) / 0.25) * a
            y = y0 + 112 + 58 * i
            text(d, (x0 + 26, y), dt, F(GOTH_B, 26), CYAN, anchor="ls", alpha=ai)
            text(d, (x0 + 120, y), fit_text(d, s, F(GOTH_R, 26), 490), F(GOTH_R, 26), INK, anchor="ls", alpha=ai)
        text(d, (x0 + 26, y0 + 538), "夜に書き足し、朝に読んでから始める", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=cl((t - e0 - 1.2) / 0.3) * a)
    caption(d, "C9", t, False)
    return flatten(f, ov)


# ------------------------------------------------------------------ C10 締め
def c10(t, D):
    ke = narr_end("C10") - 0.2
    kt = kw("C10", "見えない", ke - 1.5)
    z = 1 + 0.08 * (t / D)
    f3, _ = cam(Z8, z, (Z8.width / 2 - 80 * (z - 1) / 0.08, Z8.height / 2))
    kp = smooth((t - kt) / 0.9)
    f = blend(f3, bg(), kp)
    ov = new_ov(); d = ImageDraw.Draw(ov)
    if kp > 0:
        s = "見えない間合いを、見えるように。"
        k = back((t - kt) / 0.7)
        text(d, (640, 300), s, F(GOTH_B, 52), INK, anchor="ms", alpha=cl((t - kt) / 0.3))
        seg(d, (330, 330), (330 + 620 * ease((t - kt - 0.3) / 0.6), 330), 1, CYAN, 6)
        text(d, (640, 392), "MAAI（間合い）", F(GOTH_B, 34), CYAN, anchor="ms", alpha=cl((t - kt - 1.0) / 0.5))
        a2 = cl((t - kt - 1.6) / 0.5)
        text(d, (640, 560), "データはすべて合成です。実在の事業者・設備・図面は含みません。", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a2)
        text(d, (640, 596), f"読み上げ {T['credit']}", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a2)
        text(d, (640, 632), "github.com/Daxion1578/Minimum-Approach-Area-Indicator", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a2)
    if kp < 0.05:
        caption(d, "C10", t, True)
    return flatten(f, ov)


SCENES = {"C1": c1, "C2": c2, "C3": c3, "C4": c4,
          "C5": rec_scene("C5", (1, "図面を読む"), plan_c5, over_c5),
          "C6": rec_scene("C6", (2, "停止範囲"), plan_c6, over_c6),
          "C7": rec_scene("C7", (3, "重機の配置"), plan_c7, over_c7),
          "C8": rec_scene("C8", (4, "計画の確定"), plan_c8, over_c8),
          "C9": c9, "C10": c10}


# ------------------------------------------------------------------ 音: 冒頭は低い持続音、C4 の名前から明るい曲、締めは柔らかく
def fft_conv(x, h):
    n = len(x) + len(h) - 1; N = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(h, N), N)[: len(x)]


def reverb(x, secs=1.6, mix=0.25):
    n = int(secs * SR); rng = np.random.default_rng(3)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.32 * SR)); ir /= np.sqrt((ir ** 2).sum())
    return (1 - mix) * x + mix * fft_conv(x, ir)


def bgm8(total, t_drop, t_soft):
    N = int(total * SR); t = np.arange(N) / SR; out = np.zeros(N)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    def note(f0, at, dur, amp, harm=(1, 0.0, 0.0, 0.25), tau=0.3):
        i0 = int(at * SR); n = min(N - i0, int(dur * SR))
        if n <= 0 or i0 < 0: return
        tt = np.arange(n) / SR; env = np.exp(-tt / tau) * np.minimum(1, tt / 0.004)
        out[i0:i0 + n] += amp * env * sum(a * np.sin(2 * np.pi * f0 * (h + 1) * tt) for h, a in enumerate(harm) if a)
    # 冒頭: 低い持続音（不安）
    dr = (0.05 * np.sin(2 * np.pi * hz(38) * t) + 0.03 * np.sin(2 * np.pi * hz(45) * t)) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.15 * t))
    out += dr * (1 - smooth_arr((t - t_drop + 0.6) / 0.8))
    # 明るい曲（112 拍、木琴のような音、低音、軽い打楽器）
    beat = 60 / 112; prog = [[60, 64, 67, 72], [55, 59, 62, 67], [57, 60, 64, 69], [53, 57, 60, 65]]   # C G Am F
    k = 0; at = t_drop
    rng = np.random.default_rng(11)
    while at < total:
        ch = prog[k % 4]; soft = at >= t_soft
        for j in range(8):
            ta = at + j * beat / 2
            mn = ch[[0, 1, 2, 3, 2, 1, 2, 3][j]] + 12
            note(hz(mn), ta, 0.6, 0.045 if not soft else 0.03, harm=(1, 0, 0, 0.3), tau=0.22)
        note(hz(ch[0] - 24), at, 4 * beat, 0.09, harm=(1, 0.2), tau=0.9)
        note(hz(ch[0] - 24), at + 2.5 * beat, 1.2 * beat, 0.06, harm=(1, 0.2), tau=0.5)
        if not soft:
            for b in range(4):
                i0 = int((at + b * beat) * SR); n = min(N - i0, int(0.25 * SR))
                if n > 0:
                    tt = np.arange(n) / SR; fk = 52 * np.exp(-tt / 0.05) + 40
                    out[i0:i0 + n] += (0.10 if b % 2 == 0 else 0.05) * np.sin(2 * np.pi * np.cumsum(fk) / SR) * np.exp(-tt / 0.12)
                i1 = int((at + b * beat + beat / 2) * SR); n1 = min(N - i1, int(0.05 * SR))
                if n1 > 0:
                    nz = rng.standard_normal(n1); nz = nz - np.convolve(nz, np.ones(4) / 4, "same")
                    out[i1:i1 + n1] += 0.018 * nz * np.exp(-np.arange(n1) / SR / 0.015)
        for mn in ch:   # 柔らかい和音
            i0 = int(at * SR); n = min(N - i0, int(4 * beat * SR))
            if n > 0:
                tt = np.arange(n) / SR; env = np.minimum(1, tt / 0.4) * np.minimum(1, (4 * beat - tt) / 0.4)
                out[i0:i0 + n] += 0.008 * env * np.sin(2 * np.pi * hz(mn) * tt)
        at += 4 * beat; k += 1
    out = reverb(out, 1.6, 0.25)
    return out * np.minimum(1, t / 1.5) * np.minimum(1, (total - t) / 3.0)


def smooth_arr(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)


def se(kind):
    dur = {"click": 0.08, "whoosh": 0.6, "zap": 0.9, "done": 0.5}[kind]
    tt = np.arange(int(dur * SR)) / SR; rng = np.random.default_rng(7)
    if kind == "click":
        return 0.05 * np.sin(2 * np.pi * 2200 * tt) * np.exp(-tt / 0.01) + 0.03 * np.sin(2 * np.pi * 900 * tt) * np.exp(-tt / 0.02)
    if kind == "whoosh":
        nz = rng.standard_normal(len(tt)); nz = np.convolve(nz, np.ones(30) / 30, "same")
        return 0.05 * nz * np.sin(np.pi * tt / dur) ** 2
    if kind == "done":
        return 0.06 * (np.sin(2 * np.pi * 784 * tt) + 0.6 * np.sin(2 * np.pi * 1175 * tt)) * np.exp(-tt / 0.18) * np.minimum(1, tt / 0.005)
    nz = rng.standard_normal(len(tt)); hp = nz - np.convolve(nz, np.ones(8) / 8, "same")
    gate = (rng.random(len(tt) // 300 + 1) > 0.5).repeat(300)[: len(tt)]
    return 0.07 * hp * gate * np.exp(-tt / 0.32) * np.minimum(1, tt / 0.004) + 0.05 * np.sin(2 * np.pi * 58 * tt) * np.exp(-tt / 0.22)


def audio_file(stem):
    """作り直した .wav があればそれを、無ければリポジトリに入れた .flac を使う。"""
    w = stem.with_suffix(".wav")
    return w if w.exists() else stem.with_suffix(".flac")


def read_mono(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def mix_audio(path):
    N = int(TOTAL * SR) + SR
    narr = np.zeros(N); speech = np.zeros(N, bool)
    for x in ACTS:
        y = read_mono(audio_file(HERE / "audio" / V / f"p{PARS[x['act']]['p']:02d}"))
        i0 = int(x["n0"] * SR); n = min(len(y), N - i0)
        narr[i0:i0 + n] += y[:n]; speech[i0:i0 + n] = True
    rms = np.sqrt(np.mean(narr[speech] ** 2)) if speech.any() else 0.1
    narr *= 10 ** (-20 / 20) / max(rms, 1e-6)
    t_drop = ACT["C4"]["start"] + kw("C4", "間合い", 2.5)
    music = bgm8(N / SR, t_drop, ACT["C10"]["start"])[:N]
    if len(music) < N: music = np.pad(music, (0, N - len(music)))
    seg_after = music[int(t_drop * SR):]
    music *= 10 ** (-35 / 20) / (np.sqrt(np.mean(seg_after ** 2)) + 1e-9)        # 曲の所の RMS を語りより 15 dB 下
    duck = np.convolve(np.where(speech, 10 ** (-7 / 20), 1.0), np.ones(int(0.25 * SR)) / int(0.25 * SR), "same")
    music *= duck
    fx = np.zeros(N)
    def put(at, s, g=1.0):
        i0 = int(at * SR); n = min(len(s), N - i0)
        if n > 0: fx[i0:i0 + n] += g * s[:n]
    put(ACT["C2"]["start"] + kw("C2", "飛び移る", 4.8), se("zap"))
    put(t_drop - 0.25, se("whoosh"))
    for act in ("C5", "C6", "C7", "C8"):
        segs, zooms, ripples = PLANS.get(act) or {"C5": plan_c5, "C6": plan_c6, "C7": plan_c7, "C8": plan_c8}[act](ACT[act]["dur"])
        for at, _ in ripples: put(ACT[act]["start"] + at, se("click"))
    put(ACT["C8"]["start"] + kw("C8", "段取り", ACT["C8"]["dur"] - 2.5), se("done"))
    fx *= 10 ** (-4 / 20)
    y = np.clip(narr + music + fx, -0.98, 0.98)
    st = (np.stack([y, y], 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(st.tobytes())


# ------------------------------------------------------------------ 書き出し
def frame_at(gt):
    _frame_boxes.clear()
    for x in ACTS:
        if x["start"] <= gt < x["start"] + x["dur"]:
            t = gt - x["start"]; D = x["dur"]
            fr = SCENES[x["act"]](t, D)
            caps = [b for b, c, s in _frame_boxes if c]
            for b, c, s in _frame_boxes:
                if c: continue
                for cb in caps:
                    if b[0] < cb[2] and cb[0] < b[2] and b[1] < cb[3] and cb[1] < b[3]:
                        WARN["cap"].add(f"{x['act']}: {s[:20]}")
            i = ORDER.index(x["act"])
            fin = i == 0 or (ORDER[i - 1], x["act"]) not in NOFADE
            fout = i == len(ORDER) - 1 or (x["act"], ORDER[i + 1]) not in NOFADE
            k = min(cl(t / 0.2) if fin else 1.0, cl((D - t) / 0.2) if fout else 1.0)
            return fr if k >= 1 else Image.blend(bg(), fr, k)
    return bg()


def report():
    if WARN["small"]: print("点検: 24px 未満の字", sorted(WARN["small"]))
    if WARN["out"]: print("点検: はみ出す字", sorted(WARN["out"]))
    if WARN["cap"]: print("点検: 字幕に重なる字", sorted(WARN["cap"]))
    if not any(WARN.values()): print("点検: 字の大きさ・はみ出し・字幕との重なり 問題なし")


def loudnorm(wav_in, video, out):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav_in), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    m = json.loads(r.stderr[r.stderr.rfind("{"): r.stderr.rfind("}") + 1])
    af = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
          f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(wav_in), "-c:v", "copy", "-af", af, "-ar", str(SR),
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)


def encode(path, f0, f1):
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "18" if A.res == 1080 else "20", "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)
    for i in range(f0, f1):
        p.stdin.write(frame_at(i / FPS).tobytes())
    p.stdin.close(); p.wait()


def main():
    out = Path(A.out or (HERE / "out" / f"maai-v8-{V}-{A.res}p.mp4")); out.parent.mkdir(parents=True, exist_ok=True)
    n = int(TOTAL * FPS)
    if A.part:
        i, k = map(int, A.part.split("/"))
        encode(out.with_suffix(f".part{i}.mp4"), i * n // k, (i + 1) * n // k)
        report(); return
    print(V, "合計 %.1f 秒" % TOTAL, " ".join(f"{x['act']}:{x['dur']:.1f}" for x in ACTS))
    if A.frames or A.at:
        req = [(a, ACT[a]["dur"] * fr) for a in A.frames.split(",") if a for fr in (0.3, 0.6, 0.9)]
        req += [(s.split(":")[0], float(s.split(":")[1])) for s in A.at.split(",") if s]
        for a, tt in req:
            frame_at(ACT[a]["start"] + tt).save(out.parent / f"v8-{a}-{tt:05.1f}.png")
        report(); return
    wav = out.with_suffix(".wav"); mix_audio(wav)
    procs = [subprocess.Popen([sys.executable, __file__, V, "--res", str(A.res), "--out", str(out), "--part", f"{i}/{A.jobs}"]) for i in range(A.jobs)]
    for p in procs: p.wait()
    parts = [out.with_suffix(f".part{i}.mp4") for i in range(A.jobs)]
    lst = out.with_suffix(".txt"); lst.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    vtmp = out.with_suffix(".v.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(vtmp)], check=True)
    loudnorm(wav, vtmp, out)
    for p in parts + [lst, vtmp]: p.unlink()
    print("out", out, "%.1f 秒" % TOTAL)


if __name__ == "__main__":
    main()
