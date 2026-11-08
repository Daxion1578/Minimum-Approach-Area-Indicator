"""C3 いまの決め方（v9）: 左に図面 3 枚 → 中央の人が読み込む → 頭から吹き出しで立体 → 「？」→ 立体が薄れる。

語り（scripts/self.txt の 3 段落目）: 0「いまは、3枚の図面から、」1「頭の中で立体を組み立てて決める。」
2「でも、新任の私には、まだ判断しきれない。」3「不安が残る。」。動きはすべて cue() の時刻に合わせる（秒の決め打ちはしない）。

図面: assets/c3/{sld,plan,section}.png。今の合成の図面（data/sites/SITE-01/drawings/ の SITE-01_sld.pdf と
SITE-01_layout.pdf）を pdftoppm -r 150 で PNG にし、220kV 側を切り出して線を太らせたもの（無ければ make で作り直す）。
頭の中の立体: assets/r9/gray.jpg（r9/points.json があるとき）、無ければ v8 の assets/r7/a_gray.jpg。
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

# 図面の切り出し（150 dpi の画素）: 名前, 元の PDF, 範囲
CROPS = {
    "sld": ("SITE-01_sld.pdf", (1213, 110, 2426, 800)),         # 単線結線図の 220kV 側（東線1L・2L、母線、変圧器）
    "plan": ("SITE-01_layout.pdf", (393, 683, 2483, 1883)),     # 機械器具装置図の平面図（220kV 側と変圧器）
    "section": ("SITE-01_layout.pdf", (2649, 1109, 4511, 2152)),  # 断面図 B-B（東線1L ベイ、引留鉄塔から母線まで）
}


def _prep(dst: Path, root: Path) -> None:
    """PDF から切り出しを作る（assets/c3 に無いときだけ）。"""
    dst.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        pages = {}
        for name, (pdf, box) in CROPS.items():
            if (dst / f"{name}.png").exists():
                continue
            if pdf not in pages:
                stem = Path(td) / Path(pdf).stem
                subprocess.run(["pdftoppm", "-png", "-r", "150", "-singlefile", str(root / "data/sites/SITE-01/drawings" / pdf), str(stem)], check=True)
                pages[pdf] = Image.open(f"{stem}.png").convert("L")
            im = pages[pdf].crop(box).filter(ImageFilter.MinFilter(3))   # 細い線を太らせ、小さく出しても読めるように
            im = ImageOps.autocontrast(im.resize((1100, round(1100 * im.height / im.width)), Image.LANCZOS))
            im.convert("RGB").save(dst / f"{name}.png", optimize=True)


def make(G):
    HERE = G["HERE"]
    bg, new_ov, flatten, window, tag, text, card, caption = (G[k] for k in ("bg", "new_ov", "flatten", "window", "tag", "text", "card", "caption"))
    cue, back, ease, smooth, cl, lerp, P, K, SS = (G[k] for k in ("cue", "back", "ease", "smooth", "cl", "lerp", "P", "K", "SS"))
    F, GOTH_B, GOTH_R, rounded_mask, img = (G[k] for k in ("F", "GOTH_B", "GOTH_R", "rounded_mask", "img"))
    PAPER, INK, SUBINK, WHITE, CYAN = (G[k] for k in ("PAPER", "INK", "SUBINK", "WHITE", "CYAN"))

    A3 = HERE / "assets" / "c3"
    _prep(A3, HERE.parents[2])
    DRAW = [("単線結線図", img(A3 / "sld.png")), ("平面図", img(A3 / "plan.png")), ("断面図", img(A3 / "section.png"))]
    r9 = HERE / "assets" / "r9"
    MIND = img(r9 / "gray.jpg") if (r9 / "points.json").exists() and (r9 / "gray.jpg").exists() else img(HERE / "assets" / "r7" / "a_gray.jpg")

    # 置き場（1280×720 基準）
    WX, WW, WH = 36, 300, 170                 # 図面の窓
    WY = (34, 234, 434)
    HEAD = (505, 322)                         # 人の頭の中心
    BC = (952, 250); BHW, BHH = 292, 186      # 吹き出しの中心と半分の幅・高さ（ふちの丸を除く）
    IN = (540, 320)                           # 吹き出しの中の立体の大きさ
    PUFF = ((562, 262, 9), (590, 233, 13), (624, 202, 18))
    YEL = (244, 192, 38)

    _mind = {}
    def mind_img(sw, sh):
        k = (sw, sh)
        if k not in _mind:
            a = sw / sh; iw, ih = MIND.size
            if iw / ih > a:
                cw = ih * a; box = ((iw - cw) / 2, 0, (iw + cw) / 2, ih)
            else:
                ch = iw / a; box = (0, (ih - ch) / 2, iw, (ih + ch) / 2)
            _mind[k] = MIND.resize((sw, sh), Image.BILINEAR, box=box)
            if len(_mind) > 40: _mind.pop(next(iter(_mind)))
        return _mind[k]

    def bubble(d, s, alpha):
        """考えごとの吹き出し（ふちが丸く波打つ雲）。s は大きさ 0〜1。"""
        if s <= 0.04 or alpha <= 0: return
        x0, y0, x1, y1 = BC[0] - BHW * s, BC[1] - BHH * s, BC[0] + BHW * s, BC[1] + BHH * s
        r = 24 * s; lw = 2.6
        pts = []
        nx = max(3, round((x1 - x0) / (1.55 * max(r, 1))))
        ny = max(2, round((y1 - y0) / (1.55 * max(r, 1))))
        for i in range(nx + 1):
            x = lerp(x0, x1, i / nx); pts += [(x, y0), (x, y1)]
        for j in range(1, ny):
            y = lerp(y0, y1, j / ny); pts += [(x0, y), (x1, y)]
        oa, fa = int(200 * alpha), int(250 * alpha)
        for (x, y) in pts:
            d.ellipse([P(x - r - lw), P(y - r - lw), P(x + r + lw), P(y + r + lw)], fill=INK + (oa,))
        d.rectangle([P(x0 - lw), P(y0 - lw), P(x1 + lw), P(y1 + lw)], fill=INK + (oa,))
        for (x, y) in pts:
            d.ellipse([P(x - r), P(y - r), P(x + r), P(y + r)], fill=WHITE + (fa,))
        d.rectangle([P(x0), P(y0), P(x1), P(y1)], fill=WHITE + (fa,))

    def person(d, a, dy):
        if a <= 0: return
        hx, hy = HEAD[0], HEAD[1] + dy; ia = int(235 * a)
        d.rounded_rectangle([P(hx - 67), P(hy + 50), P(hx + 67), P(600 + dy)], int(P(56)), fill=INK + (ia,))    # 肩から胸
        d.ellipse([P(hx - 40), P(hy - 40), P(hx + 40), P(hy + 40)], fill=INK + (ia,))                             # 頭
        d.pieslice([P(hx - 46), P(hy - 50), P(hx + 46), P(hy + 42)], 180, 360, fill=YEL + (int(250 * a),))        # 保護帽
        d.rounded_rectangle([P(hx - 54), P(hy - 8), P(hx + 54), P(hy + 1)], int(P(4)), fill=YEL + (int(250 * a),))

    def scene(t, D):
        (c0a, c0b), (c1a, c1b), (c2a, c2b), (c3a, c3b) = (cue("C3", i) for i in range(4))
        f = bg(PAPER); ov = new_ov(); d = ImageDraw.Draw(ov)
        # 1) 左に図面 3 枚（上から順に滑り込む）
        for i, (name, src) in enumerate(DRAW):
            k = back((t - 0.12 * i) / 0.55)
            if k <= 0: continue
            x = lerp(-WW - 40, WX, k)
            window(f, src, (0, 0, src.width, src.height), (x, WY[i], WW, WH), radius=10)
            tag(d, (x + 10, WY[i] + WH - 10), name, 24, alpha=cl((t - 0.12 * i - 0.2) / 0.3))
        # 2) 人と、図面から頭へ読み込む線（2 文目の途中から薄れる）
        lay = Image.new("RGBA", ov.size, (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        kp = ease((t - (c0a + 0.5)) / 0.5)
        person(ld, kp, lerp(24, 0, kp))
        kl = ease((t - (c0b - 0.7)) / 0.8); fade_l = 1 - smooth((t - (c1b - 0.4)) / 0.8)
        hx, hy = HEAD[0] - 44, HEAD[1] + 6
        for i in range(3):
            a0 = (WX + WW + 6, WY[i] + WH / 2)
            if kl > 0 and fade_l > 0:
                e = (lerp(a0[0], hx, kl), lerp(a0[1], hy, kl))
                ld.line([(P(a0[0]), P(a0[1])), (P(e[0]), P(e[1]))], fill=SUBINK + (int(150 * fade_l),), width=int(P(2.2)))
                if kl >= 1:   # 図面から頭へ流れる点
                    for j in range(3):
                        u = ((t - c0b) * 0.9 + j / 3 + i * 0.11) % 1.0
                        px, py = lerp(a0[0], hx, u), lerp(a0[1], hy, u)
                        ld.ellipse([P(px - 5), P(py - 5), P(px + 5), P(py + 5)], fill=CYAN + (int(230 * fade_l),))
        # 3) 頭から、ぽわぽわと吹き出し
        fade_b = 1 - 0.25 * smooth((t - (c2a + 0.4)) / 1.2)
        for i, (x, y, r) in enumerate(PUFF):
            kk = back((t - (c1a + 0.12 * i)) / 0.35)
            if kk <= 0: continue
            rr = r * kk; ab = cl((t - (c1a + 0.12 * i)) / 0.2) * fade_b
            ld.ellipse([P(x - rr - 2.6), P(y - rr - 2.6), P(x + rr + 2.6), P(y + rr + 2.6)], fill=INK + (int(200 * ab),))
            ld.ellipse([P(x - rr), P(y - rr), P(x + rr), P(y + rr)], fill=WHITE + (int(250 * ab),))
        kb = back((t - (c1a + 0.42)) / 0.55)
        bubble(ld, kb, cl((t - (c1a + 0.42)) / 0.25) * fade_b)
        f = Image.alpha_composite(f.convert("RGBA"), lay.reduce(SS)).convert("RGB")
        # 4) 吹き出しの中で立体が下から組み上がる → 3 文目から薄れてぼやける
        if kb > 0.15:
            s = min(kb, 1.0)
            sw, sh = max(8, int(IN[0] * s * K)), max(8, int(IN[1] * s * K))
            x0, y0 = int((BC[0] - IN[0] * s / 2) * K), int((BC[1] - IN[1] * s / 2) * K)
            build = ease((t - (c1a + 0.75)) / max(0.8, (c1b - c1a) - 0.6))
            kf = smooth((t - (c2a + 0.35)) / max(1.0, c3b - c2a - 0.2))
            if build > 0:
                im = mind_img(sw, sh)
                if kf > 0:
                    im = im.filter(ImageFilter.GaussianBlur(9 * kf * K))
                    im = Image.blend(im, Image.new("RGB", im.size, WHITE), 0.62 * kf)
                m = rounded_mask(sw, sh, int(14 * K * s)).copy()
                if build < 1:   # 下から組み上がる（境目は柔らかく）
                    edge = int(sh * (1 - build)); soft = max(1, int(24 * K))
                    grad = Image.linear_gradient("L").resize((sw, soft))
                    cut = Image.new("L", (sw, sh), 0)
                    cut.paste(255, (0, min(sh, edge + soft), sw, sh))
                    if edge < sh: cut.paste(grad, (0, edge))
                    m = Image.composite(m, Image.new("L", m.size, 0), cut)
                f.paste(im, (x0, y0), m)
                if s >= 0.98:
                    tag(d, (BC[0] - IN[0] / 2 + 12, BC[1] - IN[1] / 2 + 40), "頭の中の立体", 24, alpha=cl((build - 0.6) / 0.3) * (1 - 0.5 * kf))
        # 5) 立体の上に大きな「？」（2 文目の終わりから）
        kq = back((t - (c1b - 0.25)) / 0.5)
        if kq > 0:
            aq = cl((t - (c1b - 0.25)) / 0.2)
            text(d, (BC[0], BC[1] + lerp(26, 0, kq)), "？", F(GOTH_B, 150), INK, anchor="mm", stroke=6, stroke_fill=WHITE, alpha=aq)
        # 6) 本人の言葉の札（3 文目の字幕を兼ねる）
        kc = back((t - (c2a - 0.1)) / 0.5)
        if kc > 0:
            a = cl((t - (c2a - 0.1)) / 0.25); x0 = lerp(740, 700, kc)
            card(d, x0, 472, x0 + 544, 612, a, outline=CYAN, r=16, op=250)
            text(d, (x0 + 26, 516), "「新任の私には、", F(GOTH_B, 34), INK, anchor="ls", alpha=a)
            text(d, (x0 + 26, 558), "　まだ判断しきれない」", F(GOTH_B, 34), INK, anchor="ls", alpha=a)
            text(d, (x0 + 26, 596), "作った人（変電所の工事担当）", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a)
        caption(d, "C3", t, False, skip=(2,))
        return flatten(f, ov)

    return scene
