"""C3 いまの決め方（v9.3）: 左に図面 3 枚 → ベテラン（白い帽子）が読み込み、吹き出しにくっきりした立体
→ 新任（黄色い帽子）の吹き出しは薄い立体に「？」→「図面に残らない」の札でベテランが薄れる → 新任の言葉の札。

語り（scripts/self.txt の 3 段落目、字幕は 4 つ）: 0「いまは、ベテランが、3枚の図面から、」1「頭の中で立体を組み立てて決める」
2「その経験は、図面には残らない」3「新任の私には、まだ判断しきれない」。
2・3 は札が字幕を兼ねる。動きはすべて cue() の時刻に合わせる（秒の決め打ちはしない）。

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
    PAPER, INK, SUBINK, WHITE, CYAN, RED = (G[k] for k in ("PAPER", "INK", "SUBINK", "WHITE", "CYAN", "RED"))

    A3 = HERE / "assets" / "c3"
    _prep(A3, HERE.parents[2])
    DRAW = [("単線結線図", img(A3 / "sld.png")), ("平面図", img(A3 / "plan.png")), ("断面図", img(A3 / "section.png"))]
    r9 = HERE / "assets" / "r9"
    MIND = img(r9 / "gray.jpg") if (r9 / "points.json").exists() and (r9 / "gray.jpg").exists() else img(HERE / "assets" / "r7" / "a_gray.jpg")

    # 置き場（1280×720 基準）
    WX, WW, WH = 36, 300, 170                 # 図面の窓（C4 はこの左の列から始まる）
    WY = (34, 234, 434)
    HV, HN = (476, 404), (1002, 404)          # ベテラン・新任の頭の中心
    BV, BVH = (604, 178), (200, 112)          # ベテランの吹き出し（中心と半分の幅・高さ）
    BN, BNH = (1062, 178), (164, 104)         # 新任の吹き出し
    YEL, GRAY = (244, 192, 38), (238, 238, 234)

    _mind = {}
    def mind_img(sw, sh, haze=0.0):
        k = (sw, sh, round(haze, 2))
        if k not in _mind:
            a = sw / sh; iw, ih = MIND.size
            if iw / ih > a:
                cw = ih * a; box = ((iw - cw) / 2, 0, (iw + cw) / 2, ih)
            else:
                ch = iw / a; box = (0, (ih - ch) / 2, iw, (ih + ch) / 2)
            im = MIND.resize((sw, sh), Image.BILINEAR, box=box)
            if haze > 0:
                im = im.filter(ImageFilter.GaussianBlur(8 * haze * K))
                im = Image.blend(im, Image.new("RGB", im.size, WHITE), 0.6 * haze)
            _mind[k] = im
            if len(_mind) > 60: _mind.pop(next(iter(_mind)))
        return _mind[k]

    def bubble(d, c, hh, s, alpha):
        """考えごとの吹き出し（ふちが丸く波打つ雲）。c は中心、hh は半分の幅・高さ、s は大きさ 0〜1。"""
        if s <= 0.04 or alpha <= 0: return
        x0, y0, x1, y1 = c[0] - hh[0] * s, c[1] - hh[1] * s, c[0] + hh[0] * s, c[1] + hh[1] * s
        r = 20 * s; lw = 2.4
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

    def puffs(d, head, c, hh, t0, t, alpha):
        """頭から吹き出しへ、小さな丸を 3 つ。"""
        bx, by = c[0] - hh[0] * 0.55, c[1] + hh[1] + 14
        hx, hy = head[0] + 34, head[1] - 52
        for i, r in enumerate((8, 11, 15)):
            kk = back((t - (t0 + 0.12 * i)) / 0.35)
            if kk <= 0: continue
            u = (i + 1) / 4
            x, y = lerp(hx, bx, u), lerp(hy, by, u)
            rr = r * kk; ab = cl((t - (t0 + 0.12 * i)) / 0.2) * alpha
            d.ellipse([P(x - rr - 2.4), P(y - rr - 2.4), P(x + rr + 2.4), P(y + rr + 2.4)], fill=INK + (int(200 * ab),))
            d.ellipse([P(x - rr), P(y - rr), P(x + rr), P(y + rr)], fill=WHITE + (int(250 * ab),))

    def person(d, head, a, dy, hat):
        if a <= 0: return
        hx, hy = head[0], head[1] + dy; ia = int(235 * a)
        d.rounded_rectangle([P(hx - 64), P(hy + 48), P(hx + 64), P(624 + dy)], int(P(54)), fill=INK + (ia,))    # 肩から胸
        d.ellipse([P(hx - 38), P(hy - 38), P(hx + 38), P(hy + 38)], fill=INK + (ia,))                             # 頭
        ha = int(250 * a)
        d.pieslice([P(hx - 46), P(hy - 50), P(hx + 46), P(hy + 40)], 180, 360, fill=hat + (ha,), outline=INK + (ha,), width=int(P(2.5)))   # 保護帽
        d.rounded_rectangle([P(hx - 54), P(hy - 9), P(hx + 54), P(hy + 1)], int(P(4)), fill=hat + (ha,), outline=INK + (ha,), width=int(P(2)))

    def paste_mind(f, c, hh, s, build, haze, alpha):
        """吹き出しの中に頭の中の立体を置く（build: 下から組み上がる 0〜1、alpha: 薄れ）。"""
        if s <= 0.15 or build <= 0 or alpha <= 0: return
        iw, ih = (hh[0] * 2 - 28) * min(s, 1), (hh[1] * 2 - 20) * min(s, 1)
        sw, sh = max(8, int(iw * K)), max(8, int(ih * K))
        x0, y0 = int((c[0] - iw / 2) * K), int((c[1] - ih / 2) * K)
        im = mind_img(sw, sh, haze)
        m = rounded_mask(sw, sh, int(12 * K * s)).copy()
        if build < 1:   # 下から組み上がる（境目は柔らかく）
            edge = int(sh * (1 - build)); soft = max(1, int(22 * K))
            grad = Image.linear_gradient("L").resize((sw, soft))
            cut = Image.new("L", (sw, sh), 0)
            cut.paste(255, (0, min(sh, edge + soft), sw, sh))
            if edge < sh: cut.paste(grad, (0, edge))
            m = Image.composite(m, Image.new("L", m.size, 0), cut)
        if alpha < 1:
            m = m.point(lambda v: int(v * alpha))
        f.paste(im, (x0, y0), m)

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
        # 2) ベテランが薄れていく割合（50 代の札から）
        fv = smooth((t - (c2a + 0.3)) / 2.6)
        av = 1 - 0.72 * fv                    # ベテランの濃さ
        ab_v = 1 - smooth((t - (c2a - 0.1)) / 0.45)   # ベテランの吹き出しはすぐ消えて、50 代の札に替わる
        lay = Image.new("RGBA", ov.size, (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        kpv = ease((t - (c0a + 0.35)) / 0.5)
        person(ld, HV, kpv * av, lerp(24, 0, kpv), WHITE)
        kpn = ease((t - (c0a + 0.85)) / 0.5)
        person(ld, HN, kpn, lerp(24, 0, kpn), YEL)
        # 図面からベテランの頭へ読み込む線（2 文目の途中から薄れる）
        kl = ease((t - (c0b - 0.7)) / 0.8); fade_l = 1 - smooth((t - (c1b - 0.4)) / 0.8)
        hx, hy = HV[0] - 42, HV[1] + 6
        for i in range(3):
            a0 = (WX + WW + 6, WY[i] + WH / 2)
            if kl > 0 and fade_l > 0:
                e = (lerp(a0[0], hx, kl), lerp(a0[1], hy, kl))
                ld.line([(P(a0[0]), P(a0[1])), (P(e[0]), P(e[1]))], fill=SUBINK + (int(150 * fade_l),), width=int(P(2.2)))
                if kl >= 1:
                    for j in range(3):
                        u = ((t - c0b) * 0.9 + j / 3 + i * 0.11) % 1.0
                        px, py = lerp(a0[0], hx, u), lerp(a0[1], hy, u)
                        ld.ellipse([P(px - 5), P(py - 5), P(px + 5), P(py + 5)], fill=CYAN + (int(230 * fade_l),))
        # 3) 吹き出し: ベテランは 2 文目の頭から、新任は少し遅れて
        puffs(ld, HV, BV, BVH, c1a, t, ab_v)
        kbv = back((t - (c1a + 0.42)) / 0.55)
        bubble(ld, BV, BVH, kbv, cl((t - (c1a + 0.42)) / 0.25) * ab_v)
        tn = c1a + 0.9
        puffs(ld, HN, BN, BNH, tn, t, 1.0)
        kbn = back((t - (tn + 0.42)) / 0.55)
        bubble(ld, BN, BNH, kbn, cl((t - (tn + 0.42)) / 0.25))
        f = Image.alpha_composite(f.convert("RGBA"), lay.reduce(SS)).convert("RGB")
        # 4) 吹き出しの中の立体: ベテランはくっきり組み上がる、新任は薄くぼやけたまま
        build_v = ease((t - (c1a + 0.75)) / max(0.8, (c1b - c1a) - 0.6))
        paste_mind(f, BV, BVH, min(kbv, 1.0), build_v, 0.0, ab_v)
        build_n = ease((t - (tn + 0.75)) / 0.9)
        paste_mind(f, BN, BNH, min(kbn, 1.0), build_n, 0.75, 1.0)
        if kbv >= 0.98 and ab_v > 0:
            tag(d, (BV[0] - BVH[0] + 18, BV[1] - BVH[1] + 34), "ベテランの頭の中", 24, alpha=cl((build_v - 0.6) / 0.3) * ab_v)
        if kbn >= 0.98:
            tag(d, (BN[0] - BNH[0] + 18, BN[1] - BNH[1] + 34), "新任の頭の中", 24, fg=INK, bg_=YEL, alpha=cl((build_n - 0.4) / 0.3))
        # 5) 新任の吹き出しに大きな「？」（2 文目の終わりから）
        kq = back((t - (c1b - 0.25)) / 0.5)
        if kq > 0:
            aq = cl((t - (c1b - 0.25)) / 0.2)
            text(d, (BN[0], BN[1] + 8 + lerp(22, 0, kq)), "？", F(GOTH_B, 120), INK, anchor="mm", stroke=6, stroke_fill=WHITE, alpha=aq)
        # 6) 経験の札（3 文目）: ベテランの吹き出しの所に、大きく（11/08 本人の指摘で、50 代の数字の札から替えた）
        ks = back((t - (c2a - 0.05)) / 0.5)
        if ks > 0:
            a = cl((t - (c2a - 0.05)) / 0.25)
            x0, y0 = BV[0] - 222, 62 + lerp(16, 0, ks)
            card(d, x0, y0, x0 + 444, y0 + 200, a, outline=RED, r=16, op=250)
            text(d, (x0 + 24, y0 + 48), "ベテランの頭の中の立体は", F(GOTH_R, 28), SUBINK, anchor="ls", alpha=a)
            text(d, (x0 + 24, y0 + 120), "図面に", F(GOTH_B, 44), INK, anchor="ls", alpha=a)
            text(d, (x0 + 24, y0 + 174), "残らない", F(GOTH_B, 52), RED, anchor="ls", alpha=a)
        # 7) 新任の言葉の札（4 文目の字幕を兼ねる）: 左下、薄れたベテランの前に
        kc = back((t - (c3a - 0.1)) / 0.5)
        if kc > 0:
            a = cl((t - (c3a - 0.1)) / 0.25); x0 = lerp(400, 370, kc)
            card(d, x0, 474, x0 + 530, 612, a, outline=CYAN, r=16, op=250)
            text(d, (x0 + 24, 518), "「新任の私には、", F(GOTH_B, 34), INK, anchor="ls", alpha=a)
            text(d, (x0 + 24, 560), "　まだ判断しきれない」", F(GOTH_B, 34), INK, anchor="ls", alpha=a)
            text(d, (x0 + 24, 598), "作った人（変電所の工事担当）", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a)
        caption(d, "C3", t, False, skip=(2, 3))
        return flatten(f, ov)

    return scene
