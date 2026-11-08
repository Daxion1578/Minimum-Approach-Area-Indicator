"""C2 見えない危険（v9）。

灰の 3D → 目に見えない充電部が赤く浮かぶ → クレーンが入り「ふつうの工事のように、そばに置けない」→
近づきすぎて閃絡し、クレーンを伝って感電 → 二つの影響の札（左: 人 35 件、右: 公共 送電線の先の需要家・発電事業者）。

静止画は assets/r9/（gray.jpg・live.jpg・crane.jpg・points.json の crane.boom_tip・crane.conductor）があればそれを、
無ければ v8 の r7（a_gray・a_live・a_crane と PJ）を使う。クレーンの形は crane と live の差から取り、閃絡のあと光を伝わせる。
秒は語りの文と言葉（cue・kw）から決めるので、仮の読み上げ・本人の声のどちらでもそのまま動く。
"""
from __future__ import annotations

import json
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def make(G):
    W, H, K, P, F = G["W"], G["H"], G["K"], G["P"], G["F"]
    GB, GR = G["GOTH_B"], G["GOTH_R"]
    INK, SUBINK, RED, GREEN, BLUE, WHITE, LIGHT = (G[k] for k in ("INK", "SUBINK", "RED", "GREEN", "BLUE", "WHITE", "LIGHT"))
    AMBER = G.get("AMBER", (226, 150, 20))
    text, tag, card, caption = G["text"], G["tag"], G["card"], G["caption"]
    cue, kw, ease, smooth, back, lerp, cl = G["cue"], G["kw"], G["ease"], G["smooth"], G["back"], G["lerp"], G["cl"]
    new_ov, flatten, blend, cam, s2s, zap, bg = G["new_ov"], G["flatten"], G["blend"], G["cam"], G["s2s"], G["zap"], G["bg"]
    FPS, HERE, ACT = G["FPS"], G["HERE"], G["ACT"]

    # ------------------------------------------------------------ 素材（r9 があれば r9、無ければ r7）
    R9 = HERE / "assets" / "r9"
    names = ("gray.jpg", "live.jpg", "crane.jpg")
    if (R9 / "points.json").exists() and all((R9 / n).exists() for n in names):
        S_G, S_L, S_C = (Image.open(R9 / n).convert("RGB") for n in names)
        pts = json.loads((R9 / "points.json").read_text(encoding="utf-8"))
        cr = pts.get("crane", pts)

        def pt(keys):
            for k in keys:
                v = cr.get(k)
                if v is None: continue
                return (float(v["x"]), float(v["y"])) if isinstance(v, dict) else (float(v[0]), float(v[1]))
            raise KeyError(f"r9/points.json に {keys[0]} が無い")
        P_TIP, P_CON = pt(("boom_tip", "tip", "rope")), pt(("conductor", "lead", "live"))
        sz = pts.get("size") or pts.get("image_size")
        if sz and tuple(sz[:2]) != S_G.size:   # 点の座標が別の大きさで書かれていれば合わせる
            sx, sy = S_G.width / sz[0], S_G.height / sz[1]
            P_TIP, P_CON = (P_TIP[0] * sx, P_TIP[1] * sy), (P_CON[0] * sx, P_CON[1] * sy)
        if S_L.size != S_G.size: S_L = S_L.resize(S_G.size)
        if S_C.size != S_G.size: S_C = S_C.resize(S_G.size)
        Z_ARC = float(pts.get("zoom_arc", 2.0))
    else:
        S_G, S_L, S_C = G["A1G"], G["A1L"], G["A1C"]
        P_TIP, P_CON = G["PJ"]["rope"], G["PJ"]["lead"]
        Z_ARC = 2.0
    SW, SH_ = S_G.size
    MID = ((P_TIP[0] + P_CON[0]) / 2, (P_TIP[1] + P_CON[1]) / 2)
    Z0 = G.get("C1Z", (1.0, 1.035))[1]          # C1 の終わりの寄りから続ける
    C0 = (SW / 2, SH_ / 2)

    # ------------------------------------------------------------ クレーンの形（crane − live の差）と、閃絡の点からの距離
    a = np.asarray(S_C, np.int16); b = np.asarray(S_L, np.int16)
    m = Image.fromarray(((np.abs(a - b).max(axis=2) > 38) * 255).astype(np.uint8))
    m = m.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
    M = np.asarray(m) > 0
    GLOW = 0.0003 < M.mean() < 0.2
    if GLOW:
        ys, xs = np.nonzero(M)
        bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        dd = np.hypot(xs - P_TIP[0], ys - P_TIP[1]).astype(np.float32)
        RMAX = float(np.percentile(dd, 99.5))
        DIST = np.full((by1 - by0, bx1 - bx0), 1e9, np.float32); DIST[ys - by0, xs - bx0] = dd
        low = ys >= ys.max() - 40                                  # いちばん下（車体・地面）に「感電」の札
        P_FAR = (float(xs[low].mean()), float(ys[low].mean()))
    else:
        RMAX, P_FAR = 1.0, (P_TIP[0], P_TIP[1] + 200)

    # ------------------------------------------------------------ 秒（語りの文と言葉から）
    c0, c1, c2, c3 = (cue("C2", i) for i in range(4))
    k_red = kw("C2", "見えない", c0[0] + 1.0)                     # 充電部が浮かぶ
    k_cr = c1[0] + 0.15                                            # クレーンが入る
    k_cmp = c1[0] + 0.45                                           # 「そばに置けない」の札
    k_zoom = c2[0] - 0.5                                           # 閃絡の所へ寄る
    k_arc = kw("C2", "飛び移り", c2[0] + 2.6)                      # 閃絡
    k_flow = max(k_arc + 0.9, kw("C2", "伝って", k_arc + 1.0) - 0.15)   # クレーンを伝う
    k_imp = c3[0] - 0.35                                           # 影響の札へ
    k_man = kw("C2", "命", c3[0] + 0.3) - 0.35
    k_pub = kw("C2", "設備", c3[0] + 1.8) - 0.35
    k_stop = kw("C2", "止まれば", k_pub + 0.8)
    k_dem = kw("C2", "需要家", k_stop + 1.2)
    G["SE_AT"]["C2"] = [(k_arc, "zap")]

    # 寄りの段: 閃絡の所 → クレーン全体（閃絡の点と車体が両方入る寄り）
    dx, dy = abs(P_FAR[0] - MID[0]), abs(P_FAR[1] - MID[1])
    Z_FLOW = cl(min(SW / max(1.0, dx * 1.5), SH_ / max(1.0, dy * 1.6)), 1.0, Z_ARC)
    C_FLOW = ((P_FAR[0] + MID[0]) / 2, (P_FAR[1] + MID[1]) / 2)

    def camera(t, D):
        z = lerp(Z0, Z0 * 1.06, cl(t / max(0.1, k_zoom)))
        c = C0
        u = smooth((t - k_zoom) / 1.6)
        z, c = lerp(z, Z_ARC, u), (lerp(c[0], MID[0], u), lerp(c[1], MID[1], u))
        v = smooth((t - k_flow + 0.25) / 1.4)
        z, c = lerp(z, Z_FLOW, v), (lerp(c[0], C_FLOW[0], v), lerp(c[1], C_FLOW[1], v))
        z *= 1 - 0.05 * smooth((t - k_imp) / max(0.5, D - k_imp))
        return z, c

    def glow(f, z, c, t):
        """閃絡の点からクレーンの形に沿って広がる光（前の縁が明るく、通った所は薄く残る）。"""
        if not GLOW: return f
        u = (t - k_flow) / 1.25
        if u <= 0: return f
        fade = 1 - cl((t - k_flow - 1.6) / 1.0)
        if fade <= 0: return f
        R = RMAX * ease(u); w = 0.07 * RMAX
        al = np.exp(-((DIST - R) / w) ** 2) + 0.42 * (DIST < R)
        if u < 1: al *= 0.75 + 0.25 * math.sin(t * 40)            # ちらつき
        A = Image.new("L", (SW, SH_), 0)
        A.paste(Image.fromarray(np.clip(al * 255 * fade, 0, 255).astype(np.uint8), "L"), (bx0, by0))
        A, _ = cam(A, z, c)
        halo = A.filter(ImageFilter.GaussianBlur(9 * K)).point(lambda v: int(v * 0.8))
        f = Image.composite(Image.new("RGB", f.size, (255, 214, 110)), f, halo)
        return Image.composite(Image.new("RGB", f.size, (255, 248, 214)), f, A.filter(ImageFilter.GaussianBlur(1.6 * K)))

    # ------------------------------------------------------------ 札
    def compare_card(d, t):
        """「ふつうの工事 そばに置ける」「変電所 そばに置けない」。"""
        a = cl((t - k_cmp) / 0.25) * (1 - cl((t - (c2[0] + 0.2)) / 0.3))
        if a <= 0: return
        u = back((t - k_cmp) / 0.55); x0, y0 = lerp(-560, 48, u), 48
        f30 = F(GB, 30)
        w1 = max(d.textlength("ふつうの工事", font=f30), d.textlength("変電所", font=f30)) / P(1)
        w2 = max(d.textlength("そばに置ける", font=f30), d.textlength("そばに置けない", font=f30)) / P(1)
        x1 = x0 + 96 + w1 + 30 + w2 + 34
        card(d, x0, y0, x1, y0 + 160, a, outline=(200, 212, 224), r=18, op=246)
        for i, (lab, res, col) in enumerate((("ふつうの工事", "そばに置ける", GREEN), ("変電所", "そばに置けない", RED))):
            y = y0 + 64 + 62 * i; cx, cy = x0 + 50, y - 11
            if i == 0:
                d.ellipse([P(cx - 15), P(cy - 15), P(cx + 15), P(cy + 15)], outline=col + (int(255 * a),), width=int(P(5)))
            else:
                for s in (1, -1):
                    d.line([(P(cx - 14), P(cy - 14 * s)), (P(cx + 14), P(cy + 14 * s))], fill=col + (int(255 * a),), width=int(P(6)))
            text(d, (x0 + 96, y), lab, f30, INK, anchor="ls", alpha=a)
            text(d, (x0 + 96 + w1 + 30, y), res, f30, col, anchor="ls", alpha=a)

    def person_card(d, t, x0, y0, x1, y1):
        a = ease((t - k_man) / 0.4)
        if a <= 0: return
        dy = lerp(28, 0, a); y0 += dy; y1 += dy
        card(d, x0, y0, x1, y1, a, outline=(214, 222, 230), r=18, op=250)
        tag(d, (x0 + 26, y0 + 64), "人", 30, fg=WHITE, bg_=RED, alpha=a)
        text(d, (x0 + 92, y0 + 60), "命にかかわる", F(GB, 32), INK, anchor="ls", alpha=a)
        text(d, (x0 + 26, y0 + 214), "35", F(GB, 112), RED, anchor="ls", alpha=a)
        nx = x0 + 26 + d.textlength("35", font=F(GB, 112)) / P(1) + 6
        text(d, (nx, y0 + 210), "件", F(GB, 48), RED, anchor="ls", alpha=a)
        text(d, (nx + 70, y0 + 150), "感電死傷の", F(GB, 30), INK, anchor="ls", alpha=a)
        text(d, (nx + 70, y0 + 194), "重大事故", F(GB, 30), INK, anchor="ls", alpha=a)
        text(d, (x0 + 26, y0 + 270), "令和4〜7年度に報告", F(GR, 26), SUBINK, anchor="ls", alpha=a)
        text(d, (x0 + 26, y0 + 312), "出典 経済産業省の注意喚起（2026年6月）", F(GR, 24), SUBINK, anchor="ls", alpha=a)

    def public_card(d, t, x0, y0, x1, y1):
        a = ease((t - k_pub) / 0.4)
        if a <= 0: return
        dy = lerp(28, 0, a); y0 += dy; y1 += dy
        card(d, x0, y0, x1, y1, a, outline=(214, 222, 230), r=18, op=250)
        tag(d, (x0 + 26, y0 + 64), "公共", 30, fg=WHITE, bg_=BLUE, alpha=a)
        text(d, (x0 + 122, y0 + 60), "設備が止まる", F(GB, 32), INK, anchor="ls", alpha=a)
        st = smooth((t - k_stop) / 0.35)            # 止まる（線が灰に、変電所に「停止」）
        dm = smooth((t - k_dem) / 0.35)             # 送電線の先に影響
        A = lambda v=1.0: int(255 * a * v)
        sx, sy, ly, iy = x0 + 82, y0 + 196, y0 + 140, y0 + 202
        on = tuple(int(lerp(c_, g_, st)) for c_, g_ in zip((0, 150, 199), (168, 178, 188)))
        # 変電所（鉄構と変圧器）
        for xx in (sx - 34, sx + 34):
            d.line([(P(xx), P(ly)), (P(xx), P(sy + 34))], fill=INK + (A(),), width=int(P(5)))
        d.line([(P(sx - 42), P(ly)), (P(sx + 42), P(ly))], fill=INK + (A(),), width=int(P(5)))
        d.rounded_rectangle([P(sx - 22), P(sy - 8), P(sx + 22), P(sy + 34)], int(P(4)), fill=(112, 122, 134, A()))
        d.line([(P(sx - 52), P(sy + 36)), (P(sx + 52), P(sy + 36))], fill=INK + (A(),), width=int(P(4)))
        text(d, (sx, y0 + 270), "変電所", F(GB, 24), INK, anchor="ms", alpha=a)
        # 送電線（流れる点 → 止まると灰の破線）
        xa, xb = sx + 42, x1 - 36
        if st < 1:
            d.line([(P(xa), P(ly)), (P(xb), P(ly))], fill=on + (A(),), width=int(P(5)))
            for i in range(6):
                u = ((t * 0.55 + i / 6) % 1.0)
                px = lerp(xa, xb, u)
                d.ellipse([P(px - 5), P(ly - 5), P(px + 5), P(ly + 5)], fill=WHITE + (A(1 - st),))
        else:
            x = xa
            while x < xb:
                d.line([(P(x), P(ly)), (P(min(xb, x + 14)), P(ly))], fill=on + (A(),), width=int(P(5))); x += 24
        text(d, ((xa + x0 + 300) / 2 - 6, ly - 14), "送電線", F(GR, 24), SUBINK, anchor="ms", alpha=a)
        # 送電線の先: 家・工場（需要家）と風車（発電事業者）
        icon = tuple(int(lerp(c_, g_, dm)) for c_, g_ in zip((64, 76, 92), (176, 184, 194)))
        hx, fx, tx = x0 + 300, x0 + 388, x0 + 486
        for xx, top in ((hx, iy - 36), (fx, iy - 6), (tx, iy - 30)):
            d.line([(P(xx), P(ly)), (P(xx), P(top))], fill=on + (A(),), width=int(P(4)))
        d.rectangle([P(hx - 24), P(iy - 6), P(hx + 24), P(iy + 32)], fill=icon + (A(),))
        d.polygon([(P(hx - 32), P(iy - 4)), (P(hx), P(iy - 36)), (P(hx + 32), P(iy - 4))], fill=icon + (A(),))
        d.rectangle([P(fx - 32), P(iy - 2), P(fx + 32), P(iy + 32)], fill=icon + (A(),))
        for k in range(2):
            xs_ = fx - 32 + 32 * k
            d.polygon([(P(xs_), P(iy - 2)), (P(xs_ + 32), P(iy - 2)), (P(xs_ + 32), P(iy - 22))], fill=icon + (A(),))
        d.rectangle([P(fx + 18), P(iy - 40), P(fx + 28), P(iy - 2)], fill=icon + (A(),))
        d.line([(P(tx), P(iy - 30)), (P(tx), P(iy + 32))], fill=icon + (A(),), width=int(P(5)))
        ang = (t * 2.6 if dm <= 0 else k_dem * 2.6 + 2.6 * 0.6 * (1 - math.exp(-(t - k_dem) / 0.6))) % (2 * math.pi)
        for k in range(3):
            th = ang + k * 2 * math.pi / 3
            d.line([(P(tx), P(iy - 30)), (P(tx + 30 * math.cos(th)), P(iy - 30 + 30 * math.sin(th)))], fill=icon + (A(),), width=int(P(5)))
        d.ellipse([P(tx - 6), P(iy - 36), P(tx + 6), P(iy - 24)], fill=icon + (A(),))
        text(d, ((hx + fx) / 2, y0 + 270), "需要家", F(GB, 24), INK, anchor="ms", alpha=a)
        text(d, (tx, y0 + 270), "発電事業者", F(GB, 24), INK, anchor="ms", alpha=a)
        if st > 0:   # 変電所に「停止」
            tag(d, (sx, ly - 16), "停止", 24, fg=WHITE, bg_=RED, alpha=a * st, anchor="ms")
        if dm > 0:   # 影響の印と一言
            for xx, yy in ((hx + 26, iy - 34), (fx + 34, iy - 30), (tx + 30, iy - 44)):
                r = 13
                d.ellipse([P(xx - r), P(yy - r), P(xx + r), P(yy + r)], fill=AMBER + (A(dm),))
                text(d, (xx, yy + 9), "!", F(GB, 24), WHITE, anchor="ms", alpha=a * dm)
            text(d, (x0 + 26, y0 + 330), "送電線の先まで、影響が出る", F(GB, 30), INK, anchor="ls", alpha=a * dm)

    # ------------------------------------------------------------ 場面
    def scene(t, D):
        z, c = camera(t, D)
        kl = smooth((t - k_red) / 1.0); kc = smooth((t - k_cr) / 0.5)
        if kc >= 1:
            f, bx = cam(S_C, z, c)
        else:
            f, bx = cam(S_G, z, c)
            if kl > 0: f = blend(f, cam(S_L, z, c)[0], kl)
            if kc > 0: f = blend(f, cam(S_C, z, c)[0], kc)
        f = glow(f, z, c, t)
        di = smooth((t - k_imp) / 0.6)              # 影響の札の下は、3D をぼかして明るく
        if di > 0:
            f2 = Image.blend(f.filter(ImageFilter.GaussianBlur(5 * K)), bg(LIGHT), 0.5)
            f = blend(f, f2, di)
        ov = new_ov(); d = ImageDraw.Draw(ov)
        # 閃絡
        p1, p2 = s2s(P_TIP, bx), s2s(P_CON, bx)
        mc = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        Ls = math.hypot(p2[0] - p1[0], p2[1] - p1[1]) or 1.0
        sc = cl(70 / Ls, 1.0, 3.0)
        q1 = (mc[0] + (p1[0] - mc[0]) * sc, mc[1] + (p1[1] - mc[1]) * sc)
        q2 = (mc[0] + (p2[0] - mc[0]) * sc, mc[1] + (p2[1] - mc[1]) * sc)
        fi = int(round(t * FPS))
        if k_arc <= t < k_arc + 1.2:
            u = (t - k_arc) / 1.2; rr = lerp(18, 120, ease(u))
            d.ellipse([P(mc[0] - rr), P(mc[1] - rr), P(mc[0] + rr), P(mc[1] + rr)], outline=(255, 236, 200, int(220 * (1 - u))), width=int(P(4)))
        if k_arc <= t < k_arc + 0.9:
            zap(ov, q1, q2, fi, 0.55 + 0.45 * ((fi * 7919) % 5) / 4)
        elif t >= k_arc + 0.9 and t < k_imp:
            g = 1 - cl((t - k_arc - 0.9) / 1.4)
            if g > 0: zap(ov, q1, q2, fi // 8, 0.35 * g)
        d = ImageDraw.Draw(ov)
        # 充電部の札（目に見えない → 近づけない範囲）
        a = cl((t - k_red - 0.5) / 0.3) * (1 - cl((t - k_zoom) / 0.3))
        if a > 0:
            lab = "充電部（目に見えない）" if t < c1[0] + 0.2 else "近づけない範囲"
            tx_ = cl(p2[0] + 30, 560, 960); ty_ = cl(p2[1] - 150, 110, 330)
            d.line([(P(tx_ + 12), P(ty_ + 4)), (P(p2[0]), P(p2[1]))], fill=RED + (int(220 * a),), width=int(P(3)))
            d.ellipse([P(p2[0] - 7), P(p2[1] - 7), P(p2[0] + 7), P(p2[1] + 7)], fill=RED + (int(255 * a),), outline=WHITE + (int(255 * a),), width=int(P(2)))
            tag(d, (tx_, ty_), lab, 28, fg=WHITE, bg_=RED, alpha=a)
        compare_card(d, t)
        al = cl((t - k_arc - 0.3) / 0.3) * (1 - cl((t - k_flow) / 0.3))
        if al > 0:
            tag(d, (cl(mc[0] - 40, 120, 1240), cl(mc[1] - 24, 80, 600)), "閃絡", 30, fg=WHITE, bg_=INK, alpha=al, anchor="rs")
        ae = cl((t - k_flow - 0.45) / 0.25) * (1 - cl((t - k_imp - 0.1) / 0.3))
        if ae > 0:   # 車体の上に「感電」
            pf = s2s(P_FAR, bx)
            tag(d, (cl(pf[0], 120, 1160), cl(pf[1] - 96, 90, 560)), "感電", 30, fg=WHITE, bg_=RED, alpha=ae, anchor="ms")
        # 二つの影響
        if t > k_man - 0.05: person_card(d, t, 56, 92, 622, 470)
        if t > k_pub - 0.05: public_card(d, t, 658, 92, 1224, 470)
        caption(d, "C2", t, True)
        out = flatten(f, ov)
        if k_arc <= t < k_arc + 0.25:
            out = Image.blend(out, Image.new("RGB", (W, H), (235, 242, 255)), 0.45 * (1 - (t - k_arc) / 0.25))
        return out

    return scene
