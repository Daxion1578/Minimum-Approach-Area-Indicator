"""C1 依頼が届く（v9.3、掴み）: 灰色の 3D・取り替える遮断器の印 → 「10 t」→「クレーン 100t 級 ？」の驚き →
「決め手 ＝ 電気との間合い」→ 問い 2 つ（どこまで止める？／何トン級？）と停止の申請の期限の札。

語り（scripts/self.txt の 1 段落目、6 文）: 0 私は、変電所の工事担当。1 この遮断器を、取り替える。2 重さは10トン。
3 なのに、クレーンは100トン級。4 決め手は、重さではなく、電気との間合い。5 止める範囲とクレーンを、申請の期限までに決める。
文の時刻は言葉で探す（見つからなければ順番）。暦日は書かない（CLAUDE.md）。期限は「工事の何か月も前」（一般論として何か月とは言えない）。

assets/r9/points.json（gray.target）と r9/gray.jpg があればそれを使い、無ければ v8 の r7/a_gray.jpg と TARGET で描く。
カメラは v8 と同じ（C1Z の寄り、中心 960,540）。終わりの 0.45 秒で札を消し、C2 の始め（同じ静止画・同じ寄り）へ切れ目なくつなぐ。
"""
from __future__ import annotations

import json
import math

from PIL import Image, ImageDraw


def make(G):
    HERE = G["HERE"]
    F, GOTH_B, GOTH_R = G["F"], G["GOTH_B"], G["GOTH_R"]
    text, tag, card, seg, ripple, caption = G["text"], G["tag"], G["card"], G["seg"], G["ripple"], G["caption"]
    new_ov, flatten, P, cam, s2s, SS, K = G["new_ov"], G["flatten"], G["P"], G["cam"], G["s2s"], G["SS"], G["K"]
    cl, back, lerp, ease = G["cl"], G["back"], G["lerp"], G["ease"]
    INK, SUBINK, RED, BLUE, CYAN, WHITE = G["INK"], G["SUBINK"], G["RED"], G["BLUE"], G["CYAN"], G["WHITE"]
    AMBER = G.get("AMBER", (226, 150, 20))
    C1Z = G["C1Z"]
    cue, kw, ACT, PARS = G["cue"], G["kw"], G["ACT"], G["PARS"]

    # ---------------------------------------------------------------- 素材（r9 があれば r9）
    src, target = G["A1G"], G["TARGET"]
    r9 = HERE / "assets" / "r9"
    try:
        pts = json.loads((r9 / "points.json").read_text(encoding="utf-8"))
        g = pts.get("gray") or {}
        tg = g.get("target") if isinstance(g, dict) else None
        if isinstance(tg, dict):
            tg = (tg.get("x"), tg.get("y"))
        if tg and (r9 / "gray.jpg").exists():
            src = Image.open(r9 / "gray.jpg").convert("RGB")
            target = (float(tg[0]), float(tg[1]))
    except (OSError, ValueError, TypeError, KeyError):
        pass

    # ---------------------------------------------------------------- 文の時刻（言葉で探す。見つからなければ順番で）
    cues = PARS["C1"]["cues"]
    n = len(cues)

    def idx(word, fallback):
        for i, c in enumerate(cues):
            if word in c["text"]:
                return i
        return fallback if fallback < n else None

    def start(i, default):
        return cue("C1", i)[0] if i is not None else default

    D0 = ACT["C1"]["dur"]
    t_this = start(idx("この遮断器", 1), 1.5)
    t_w = start(idx("10トン", 2), 4.0)            # 重さは 10 t
    t_c = start(idx("100トン", 3), 5.5)            # なのに、クレーンは 100t 級
    t_k = start(idx("決め手", 4), 8.0)             # 決め手 ＝ 電気との間合い
    t_q = start(idx("期限", 5), D0 - 4.0)          # 問い 2 つと期限
    t_out = t_q - 0.15                              # 驚きの札を下げる
    t_strike = kw("C1", "ではなく", t_k + 1.1)       # 「重さ」に打ち消し線
    t_ans = kw("C1", "電気との", t_k + 1.9) - 0.15   # 「電気との間合い」

    # 取り替える遮断器の位置（真ん中の寄りで）。左半分にあれば、札は右に出す
    _, bx_mid = cam(src, lerp(C1Z[0], C1Z[1], 0.5), (960, 540))
    p_mid = s2s(target, bx_mid)
    mirror = p_mid[0] < 640
    CW = 520
    X_R = 1280 - 56 - CW if mirror else 56          # 驚き・期限の札の側
    X_Q = 56 if mirror else 1280 - 56 - 410         # 問いの札の側

    def clock(d, cx, cy, r, a, u):
        col = AMBER + (int(255 * a),)
        d.ellipse([P(cx - r), P(cy - r), P(cx + r), P(cy + r)], outline=col, width=int(P(4)))
        ang = -math.pi / 2 + 2 * math.pi * u
        d.line([(P(cx), P(cy)), (P(cx + r * 0.72 * math.cos(ang)), P(cy + r * 0.72 * math.sin(ang)))], fill=col, width=int(P(4)))
        d.line([(P(cx), P(cy)), (P(cx), P(cy - r * 0.48))], fill=col, width=int(P(4)))
        d.ellipse([P(cx - 3.5), P(cy - 3.5), P(cx + 3.5), P(cy + 3.5)], fill=col)

    def tw(d, s, f):
        return d.textlength(s, font=f) / SS / K

    def c1(t, D):
        z = lerp(C1Z[0], C1Z[1], t / D)
        f, bx = cam(src, z, (960, 540))
        ov = new_ov(); d = ImageDraw.Draw(ov)
        p = s2s(target, bx)
        down = 1 - cl((t - t_out) / 0.3)          # 驚きの札（10 t・100t 級・決め手）を下げる

        # 1) 取り替える遮断器に輪と札（「この遮断器」で輪を強める）
        a = cl((t - 0.3) / 0.3)
        if a > 0:
            period = 1.4 if t < t_this else 1.0
            ripple(d, p, ((t - 0.3) % period) / period, col=CYAN)
            if t_this - 0.1 <= t < t_this + 0.9:
                ripple(d, p, cl((t - t_this + 0.1) / 1.0) * 0.999, col=WHITE)
            d.ellipse([P(p[0] - 9), P(p[1] - 9), P(p[0] + 9), P(p[1] + 9)], fill=CYAN + (int(255 * a),), outline=WHITE + (int(255 * a),), width=int(P(3)))
            right = (not mirror) if 180 < p[0] < 1100 else p[0] <= 180
            dx = 52 if right else -52
            seg(d, (p[0] + (8 if right else -8), p[1] - 8), (p[0] + dx + (8 if right else -8), p[1] - 60), 1, CYAN, 3, alpha=a)
            tag(d, (p[0] + dx + (10 if right else -10), p[1] - 56), "20E1-110 遮断器", 26, fg=WHITE, bg_=CYAN, alpha=a, anchor="ls" if right else "rs")

        # 2) 工事の依頼（上に 1 行）
        a = cl((t - t_this + 0.1) / 0.3)
        if a > 0:
            y0 = lerp(10, 30, ease((t - t_this + 0.1) / 0.4))
            f26 = F(GOTH_B, 26)
            s = "220kV 東線1L の遮断器 20E1-110 を取り替える"
            w = 160 + tw(d, s, f26) + 30
            x0 = 640 - w / 2
            card(d, x0, y0, x0 + w, y0 + 58, a, outline=(200, 212, 224), r=14, op=244)
            tag(d, (x0 + 16, y0 + 43), "工事の依頼", 24, fg=WHITE, bg_=CYAN, alpha=a)
            text(d, (x0 + 160, y0 + 40), s, f26, INK, anchor="ls", alpha=a)

        # 3) 重さは 10 t（遮断器のそば、大きく）
        k = back((t - t_w + 0.1) / 0.45); a = cl((t - t_w + 0.1) / 0.2) * down
        if a > 0:
            bxw, byw = 290, 170
            cx = cl(p[0] + (-40 - bxw if mirror else 40), 40, 1240 - bxw)
            cy = cl(p[1] + 50, 120, 452)
            s_ = 0.85 + 0.15 * cl(k)
            card(d, cx, cy, cx + bxw * s_, cy + byw * s_, a, outline=(200, 212, 224), r=18, op=248)
            text(d, (cx + 26, cy + 50 * s_), "重さ", F(GOTH_B, 32), SUBINK, anchor="ls", alpha=a)
            text(d, (cx + 24, cy + 148 * s_), "10 t", F(GOTH_B, int(round(100 * s_))), INK, anchor="ls", alpha=a)
            seg(d, (p[0], p[1] + 10), (cx + (bxw * s_ if mirror else 0), cy + 60), 1, INK, 3, alpha=a * 0.8)

        # 4) なのに、クレーンは 100t 級 ？（右に大きく）
        k = back((t - t_c + 0.1) / 0.5); a = cl((t - t_c + 0.1) / 0.2) * down
        if a > 0:
            x0, y0 = X_R + lerp(60 if mirror else -60, 0, cl(k)), 108
            card(d, x0, y0, x0 + CW, y0 + 232, a, outline=CYAN, r=20, op=250)
            text(d, (x0 + 30, y0 + 58), "クレーン", F(GOTH_B, 34), SUBINK, anchor="ls", alpha=a)
            f_big = F(GOTH_B, 92)
            text(d, (x0 + 26, y0 + 194), "100t 級", f_big, CYAN, anchor="ls", alpha=a)
            qa = cl((t - t_c - 0.55) / 0.25)
            if qa > 0:
                text(d, (x0 + 34 + tw(d, "100t 級", f_big), y0 + 194), "？", f_big, RED, anchor="ls", alpha=a * qa)

        # 5) 決め手 ＝ 電気との間合い（「重さ」は打ち消す）
        k = back((t - t_k + 0.1) / 0.5); a = cl((t - t_k + 0.1) / 0.2) * down
        if a > 0:
            x0, y0 = X_R, lerp(392, 360, cl(k))
            card(d, x0, y0, x0 + CW, y0 + 156, a, outline=AMBER, r=18, op=250)
            f34 = F(GOTH_B, 34)
            text(d, (x0 + 28, y0 + 54), "決め手 ＝", f34, SUBINK, anchor="ls", alpha=a)
            wx = x0 + 28 + tw(d, "決め手 ＝", f34) + 18
            text(d, (wx, y0 + 54), "重さ", f34, (150, 158, 168), anchor="ls", alpha=a)
            if t > t_strike:   # 「重さではなく」で打ち消し線
                seg(d, (wx - 4, y0 + 42), (wx + tw(d, "重さ", f34) + 4, y0 + 42), ease((t - t_strike) / 0.3), RED, 4, alpha=a)
            ka = cl((t - t_ans) / 0.25)
            if ka > 0:
                text(d, (x0 + 28, y0 + 130 + 10 * (1 - ease((t - t_ans) / 0.35))), "電気との間合い", F(GOTH_B, 58), INK, anchor="ls", alpha=a * ka)

        # 6) 問い 2 つ（左）と、停止の申請の期限（右）
        for i in range(2):
            s = ("どこまで止める？", "何トン級？")[i]
            at = t_q + 0.1 + 0.25 * i
            k = back((t - at) / 0.5); a = cl((t - at) / 0.2)
            if a <= 0: continue
            y = 432 + 100 * i
            x0 = lerp(-560, X_Q, k) if mirror else lerp(1300, X_Q, k)
            card(d, x0, y - 66, x0 + 410, y + 20, a, r=16, op=246)
            d.rounded_rectangle([P(x0), P(y - 66), P(x0 + 10), P(y + 20)], int(P(4)), fill=(RED if i == 0 else BLUE) + (int(255 * a),))
            text(d, (x0 + 34, y), s, F(GOTH_B, 42), INK, anchor="ls", alpha=a)
        k = back((t - t_q - 0.5) / 0.5); a = cl((t - t_q - 0.5) / 0.2)
        if a > 0:
            x0 = X_R; y0 = lerp(170, 130, cl(k))
            card(d, x0, y0, x0 + CW, y0 + 130, a, outline=AMBER, r=16, op=250)
            d.rounded_rectangle([P(x0 - 4), P(y0 - 4), P(x0 + CW + 4), P(y0 + 134)], int(P(18)), outline=AMBER + (int(150 * a),), width=int(P(5)))
            tag(d, (x0 + 22, y0 + 50), "停止の申請", 26, fg=WHITE, bg_=AMBER, alpha=a)
            text(d, (x0 + 24, y0 + 108), "期限は、工事の何か月も前", F(GOTH_B, 34), INK, anchor="ls", alpha=a)
            clock(d, x0 + CW - 50, y0 + 44, 28, a, ease((t - t_q - 0.5) / 2.5))

        caption(d, "C1", t, True)
        out = flatten(f, ov)
        k = (D - t) / 0.45   # 終わりの 0.45 秒で札を消し、C2 の始め（同じ静止画・同じ寄り）へ切れ目なくつなぐ
        if k < 1:
            out = Image.blend(f.convert("RGB"), out, max(0.0, k))
        return out

    return c1
