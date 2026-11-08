"""C1 依頼が届く（v9）: 灰色の 3D・取り替える遮断器の印・工事の依頼の札・停止の申請期限の札・問い 2 つ。

assets/r9/points.json（gray.target）と r9/gray.jpg があればそれを使い、無ければ v8 の r7/a_gray.jpg と TARGET で描く。
カメラは v8 と同じ（C1Z の寄り、中心 960,540）。C2 はここから続ける（compose9 の NOFADE）。
文の時刻は語りの文から言葉で探す（「期限」「どこまで」「何トン」）。暦日は書かない（CLAUDE.md）。
"""
from __future__ import annotations

import json
import math

from PIL import Image, ImageDraw


def make(G):
    HERE = G["HERE"]
    F, GOTH_B, GOTH_R = G["F"], G["GOTH_B"], G["GOTH_R"]
    text, tag, card, seg, ripple, caption = G["text"], G["tag"], G["card"], G["seg"], G["ripple"], G["caption"]
    new_ov, flatten, P, cam, s2s = G["new_ov"], G["flatten"], G["P"], G["cam"], G["s2s"]
    cl, back, lerp, ease = G["cl"], G["back"], G["lerp"], G["ease"]
    INK, SUBINK, RED, BLUE, CYAN, WHITE = G["INK"], G["SUBINK"], G["RED"], G["BLUE"], G["CYAN"], G["WHITE"]
    AMBER = G.get("AMBER", (226, 150, 20))
    C1Z = G["C1Z"]
    cue, ACT, PARS = G["cue"], G["ACT"], G["PARS"]

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
    def idx(word, fallback):
        for i, c in enumerate(cues):
            if word in c["text"]:
                return i
        return fallback if fallback < len(cues) else None
    i_this, i_due, i_q1, i_q2 = idx("この遮断器", 1), idx("期限", 2), idx("どこまで", 3), idx("何トン", 4)
    def start(i, default):
        return cue("C1", i)[0] if i is not None else default
    D0 = ACT["C1"]["dur"]
    t_this, t_due = start(i_this, 1.5), start(i_due, 4.0)
    t_q1, t_q2 = start(i_q1, D0 - 4.0), start(i_q2, D0 - 2.2)
    skip = tuple(i for i in (i_q1, i_q2) if i is not None)   # 問いの札が字幕を兼ねる

    # 取り替える遮断器が札に隠れるなら、札を右に、問いを左に出す
    _, bx_mid = cam(src, lerp(C1Z[0], C1Z[1], 0.5), (960, 540))
    p_mid = s2s(target, bx_mid)
    mirror = p_mid[0] < 640

    CW = 520                                    # 札の幅（1280 基準）
    X_CARD = 1280 - 56 - CW if mirror else 56   # 依頼の札・期限の札の左端
    REQ = ["220kV 東線1L の遮断器", "20E1-110 を取り替える", "新しい遮断器は 約 10 t", "東線1L は相手端も含めて止める", "220kV 母線 A 区間は止められない"]

    def clock(d, cx, cy, r, a, u):
        """期限の札の時計。u（0〜1）で長針が回る。"""
        col = AMBER + (int(255 * a),)
        d.ellipse([P(cx - r), P(cy - r), P(cx + r), P(cy + r)], outline=col, width=int(P(4)))
        ang = -math.pi / 2 + 2 * math.pi * u
        d.line([(P(cx), P(cy)), (P(cx + r * 0.72 * math.cos(ang)), P(cy + r * 0.72 * math.sin(ang)))], fill=col, width=int(P(4)))
        d.line([(P(cx), P(cy)), (P(cx), P(cy - r * 0.48))], fill=col, width=int(P(4)))
        d.ellipse([P(cx - 3.5), P(cy - 3.5), P(cx + 3.5), P(cy + 3.5)], fill=col)

    def c1(t, D):
        z = lerp(C1Z[0], C1Z[1], t / D)
        f, bx = cam(src, z, (960, 540))
        ov = new_ov(); d = ImageDraw.Draw(ov)
        p = s2s(target, bx)

        # 1) 取り替える遮断器に輪と札（「この遮断器」で輪を強める）
        a = cl((t - 0.3) / 0.3)
        if a > 0:
            period = 1.4 if t < t_this else 1.0
            ripple(d, p, ((t - 0.3) % period) / period, col=CYAN)
            if t_this - 0.1 <= t < t_this + 0.9:
                ripple(d, p, cl((t - t_this + 0.1) / 1.0) * 0.999, col=WHITE)
            d.ellipse([P(p[0] - 9), P(p[1] - 9), P(p[0] + 9), P(p[1] + 9)], fill=CYAN + (int(255 * a),), outline=WHITE + (int(255 * a),), width=int(P(3)))
            right = (not mirror) if 180 < p[0] < 1100 else p[0] <= 180   # 札と反対の側へ
            dx = 52 if right else -52
            seg(d, (p[0] + (8 if right else -8), p[1] - 8), (p[0] + dx + (8 if right else -8), p[1] - 60), 1, CYAN, 3, alpha=a)
            tag(d, (p[0] + dx + (10 if right else -10), p[1] - 56), "20E1-110 遮断器", 26, fg=WHITE, bg_=CYAN, alpha=a, anchor="ls" if right else "rs")

        # 2) 工事の依頼の札（横から滑り込む）
        ka = 0.5; u = back((t - ka) / 0.6); a = cl((t - ka) / 0.25)
        if a > 0:
            x0 = lerp(1300 if mirror else -560, X_CARD, u); y0 = 44
            card(d, x0, y0, x0 + CW, y0 + 296, a, outline=(200, 212, 224), r=18, op=246)
            tag(d, (x0 + 22, y0 + 54), "工事の依頼", 26, fg=WHITE, bg_=CYAN, alpha=a)
            for i, s in enumerate(REQ):
                ai = cl((t - ka - 0.4 - 0.15 * i) / 0.3)
                yy = y0 + 104 + 40 * i + (8 if i >= 2 else 0)   # 1・2 行目は一つの事柄
                text(d, (x0 + 24, yy), s, F(GOTH_B, 27 if i < 2 else 25), INK if i < 2 else (40, 48, 58), anchor="ls", alpha=a * ai)

        # 3) 停止の申請の期限（3 文目で目立たせる）
        k = back((t - t_due + 0.15) / 0.5); a = cl((t - t_due + 0.15) / 0.2)
        if a > 0:
            x0 = X_CARD; y0 = lerp(396, 356, k)
            hot = cl(1 - abs(t - t_due - 1.2) / 1.6)          # 語りの間は枠を太く
            card(d, x0, y0, x0 + CW, y0 + 116, a, outline=AMBER, r=16, op=250)
            if hot > 0:
                d.rounded_rectangle([P(x0 - 4), P(y0 - 4), P(x0 + CW + 4), P(y0 + 120)], int(P(18)), outline=AMBER + (int(150 * hot * a),), width=int(P(5)))
            tag(d, (x0 + 22, y0 + 46), "停止の申請", 26, fg=WHITE, bg_=AMBER, alpha=a)
            text(d, (x0 + 24, y0 + 96), "期限は、工事の約 3 か月前", F(GOTH_B, 32), INK, anchor="ls", alpha=a)
            clock(d, x0 + CW - 56, y0 + 58, 30, a, ease((t - t_due) / 2.5))

        # 4) 問い 2 つ（画面の文字が字幕を兼ねる）
        for i, at in enumerate((t_q1, t_q2)):
            s = ("止めるのは、どこまで？", "クレーンは、何トン級？")[i]
            k = back((t - at) / 0.5); a = cl((t - at) / 0.2)
            if a <= 0: continue
            y = 452 + 100 * i
            x0 = lerp(-560, 56, k) if mirror else lerp(1300, 712, k)
            card(d, x0, y - 66, x0 + 520, y + 20, a, r=16, op=246)
            d.rounded_rectangle([P(x0), P(y - 66), P(x0 + 10), P(y + 20)], int(P(4)), fill=(RED if i == 0 else BLUE) + (int(255 * a),))
            text(d, (x0 + 34, y), s, F(GOTH_B, 42), INK, anchor="ls", alpha=a)

        caption(d, "C1", t, True, skip=skip)
        return flatten(f, ov)

    return c1
