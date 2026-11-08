"""C10 締め（v9.3）。語り（scripts/self.txt の 10 段落目、4 文）に合わせて:
0「変圧器だけで、約1万5千台」→ 大きな数字の札（明るい地、出典つき）
1「全部を替えるには、いまのペースで約70年」→ 2 枚目の札（年約 220 台のペースで全部を替える場合）
2「そのたびに、次の担当者が、この二つを決める」→ 冒頭（C1）と同じ構図の灰の 3D に、C1 の問いの札 2 枚を答えつきで
3「見えない間合いを、見えるように」→ 同じ構図のまま充電部の赤を重ねて、言葉 → 名前・注記・GitHub・読み上げの表記。
数字の札と締めの言葉は画面の文字が字幕を兼ねる（0・1・3 の文の字幕は出さない）。
読み上げの表記は timing.json の credit があるときだけ出す（声を差し替えたら credit も差し替わる）。

3D は C1 と同じ選び方（assets/r9/points.json の gray.target と r9/gray.jpg、無ければ v8 の r7/a_gray.jpg と TARGET）。
赤を重ねる r9/live.jpg は、points.json のカメラが gray と同じときだけ使う（ずれた絵を重ねない）。

compose9.py が make(G) を呼ぶ。G は compose9 の globals。
"""
from __future__ import annotations

import json

SRC = "出典: 電力広域的運営推進機関の資料（2026年9月）"
PACE = "年約 220 台のペースで、全部を替える場合"


def make(G):
    ImageDraw, Image = G["ImageDraw"], G["Image"]
    F, GOTH_B, GOTH_R = G["F"], G["GOTH_B"], G["GOTH_R"]
    text, seg, card, ripple = G["text"], G["seg"], G["card"], G["ripple"]
    bg, cue, kw, caption, cam, s2s, blend = G["bg"], G["cue"], G["kw"], G["caption"], G["cam"], G["s2s"], G["blend"]
    new_ov, flatten, narr_end, P, SS, K = G["new_ov"], G["flatten"], G["narr_end"], G["P"], G["SS"], G["K"]
    cl, lerp, ease, back, smooth = G["cl"], G["lerp"], G["ease"], G["back"], G["smooth"]
    INK, SUBINK, WHITE, CYAN, GREEN, BLUE, RED = G["INK"], G["SUBINK"], G["WHITE"], G["CYAN"], G["GREEN"], G["BLUE"], G["RED"]
    T, HERE, C1Z, PARS = G["T"], G["HERE"], G["C1Z"], G["PARS"]

    # ---------------------------------------------------------------- 素材（C1 と同じ選び方）
    src, live, target = G["A1G"], G.get("A1L"), G["TARGET"]
    r9 = HERE / "assets" / "r9"
    try:
        pts = json.loads((r9 / "points.json").read_text(encoding="utf-8"))
        tg = (pts.get("gray") or {}).get("target")
        if isinstance(tg, dict):
            tg = (tg.get("x"), tg.get("y"))
        if tg and (r9 / "gray.jpg").exists():
            src = Image.open(r9 / "gray.jpg").convert("RGB")
            target = (float(tg[0]), float(tg[1]))
            cams = pts.get("camera") or {}
            same = cams.get("gray") is not None and cams.get("live") == cams.get("gray")
            live = Image.open(r9 / "live.jpg").convert("RGB") if same and (r9 / "live.jpg").exists() else None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    if live is not None and live.size != src.size:
        live = None
    credit = T.get("credit") or ""

    # ---------------------------------------------------------------- 文の時刻
    n = len(PARS["C10"]["cues"])

    def cs(i):
        return cue("C10", min(i, n - 1))[0]

    t0, t1, t2, t3 = cs(0), cs(1), cs(2), cs(3)
    t_3d = kw("C10", "次の担当者", t2 + 1.0) - 0.5     # 3D に替わる（「そのたびに」の後）
    t_ans = kw("C10", "この二つ", t2 + 2.0)             # 答えが出る
    t_vis = kw("C10", "見えるように", t3 + 1.0)         # 赤を重ねる
    t_end = narr_end("C10")                              # 語りの終わり → 明るい地に名前など
    G["SE_AT"]["C10"] = [(t0, "click"), (t1, "click"), (t_ans, "click"), (t_ans + 0.3, "click")]

    # 取り替える遮断器の位置（真ん中の寄りで）。左半分にあれば、問いの札は C1 と同じく左に出す
    _, bx_mid = cam(src, lerp(C1Z[0], C1Z[1], 0.5), (960, 540))
    mirror = s2s(target, bx_mid)[0] < 640
    CWQ = 420
    X_Q = 56 if mirror else 1280 - 56 - CWQ
    QA = [("どこまで止める？", "ここまで", GREEN, RED), ("何トン級？", "100t 級", CYAN, BLUE)]

    def tw(d, s, f):
        return d.textlength(s, font=f) / SS / K

    def numcard(d, a, dy, label, final, shown, unit, notes):
        """明るい地の大きな数字の札。数字は右寄せの枠に入れて、数え上げても「約」「台」が動かない。"""
        if a <= 0: return
        x0, x1, y0 = 190, 1090, 136 + dy
        y1 = y0 + 318 + 34 * len(notes)
        card(d, x0, y0, x1, y1, a, outline=(200, 212, 224), r=22, op=250)
        text(d, (640, y0 + 74), label, F(GOTH_B, 36), SUBINK, anchor="ms", alpha=a)
        fa, fn = F(GOTH_B, 64), F(GOTH_B, 168)
        wa, wn, wu, gap = tw(d, "約", fa), tw(d, final, fn), tw(d, unit, fa), 18
        x = 640 - (wa + gap + wn + gap + wu) / 2; yb = y0 + 262
        text(d, (x, yb), "約", fa, INK, anchor="ls", alpha=a)
        text(d, (x + wa + gap + wn, yb), shown, fn, INK, anchor="rs", alpha=a)
        text(d, (x + wa + gap + wn + gap, yb), unit, fa, INK, anchor="ls", alpha=a)
        for j, s in enumerate(notes):
            text(d, (640, y0 + 316 + 34 * j), s, F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a)

    def scene(t, D):
        # ---- 地: 明るい地 → 灰の 3D（C1 と同じ寄り）→ 赤を重ねる → 明るい地
        kb = smooth((t - t_3d) / 0.5)
        kv = smooth((t - t_vis + 0.35) / 0.7) if live is not None else 0.0
        kp = smooth((t - t_end - 0.1) / 0.9)
        z = lerp(C1Z[0], C1Z[1], cl((t - t_3d) / 6.0))
        bx = None
        if kb <= 0:
            f = bg()
        else:
            g3, bx = cam(src, z, (960, 540))
            if kv > 0:
                l3, _ = cam(live, z, (960, 540)); g3 = blend(g3, l3, kv)
            f = blend(bg(), g3, kb)
            f = blend(f, bg(), kp)
        ov = new_ov(); d = ImageDraw.Draw(ov)

        # ---- 0・1: 大きな数字の札（1 枚ずつ）
        out1 = smooth((t - t1 + 0.3) / 0.3)
        k = back((t - t0 + 0.1) / 0.5); a = cl((t - t0 + 0.1) / 0.25) * (1 - out1)
        if a > 0:
            v = int(round(15000 * ease((t - t0) / 0.7) / 100) * 100)
            numcard(d, a, lerp(24, 0, k) - 24 * out1, "変圧器だけで", "15,000", f"{v:,}", "台", [SRC])
        out2 = smooth((t - t_3d) / 0.3)
        k = back((t - t1 + 0.2) / 0.5); a = cl((t - t1 + 0.2) / 0.25) * (1 - out2)
        if a > 0:
            v = int(round(70 * ease((t - t1) / 0.7)))
            numcard(d, a, lerp(24, 0, k) - 24 * out2, "全部を替えるには、いまのペースで", "70", f"{v}", "年", [PACE, SRC])

        # ---- 2: C1 の問いの札 2 枚に答え（取り替える遮断器の輪も C1 と同じ）
        fq = (1 - smooth((t - t3 + 0.1) / 0.35)) * kb * (1 - kp)
        if bx is not None and fq > 0:
            p = s2s(target, bx)
            ripple(d, p, ((t - t_3d) % 1.4) / 1.4, col=CYAN)
            d.ellipse([P(p[0] - 9), P(p[1] - 9), P(p[0] + 9), P(p[1] + 9)], fill=CYAN + (int(255 * fq),), outline=WHITE + (int(255 * fq),), width=int(P(3)))
            for i, (q, ans, acol, bar) in enumerate(QA):
                at = t_3d + 0.3 + 0.25 * i
                k = back((t - at) / 0.5); a = cl((t - at) / 0.2) * fq
                if a <= 0: continue
                y0 = 282 + 146 * i
                x0 = lerp(-CWQ - 40, X_Q, k) if mirror else lerp(1320, X_Q, k)
                card(d, x0, y0, x0 + CWQ, y0 + 128, a, r=16, op=246)
                d.rounded_rectangle([P(x0), P(y0), P(x0 + 10), P(y0 + 128)], int(P(4)), fill=bar + (int(255 * a),))
                text(d, (x0 + 34, y0 + 48), q, F(GOTH_B, 34), INK, anchor="ls", alpha=a)
                ta = t_ans + 0.3 * i
                u = back((t - ta) / 0.4); aa = cl((t - ta) / 0.15) * a
                if aa > 0:
                    text(d, (x0 + 34, y0 + 108), "→", F(GOTH_B, 44), SUBINK, anchor="ls", alpha=aa)
                    text(d, (x0 + 96, y0 + 110), ans, F(GOTH_B, int(round(54 * lerp(0.8, 1.0, u)))), acol, anchor="ls", alpha=aa)

        # ---- 3: 見えない間合いを、見えるように。→ 名前・注記・GitHub・読み上げの表記
        a = cl((t - t3) / 0.3)
        if a > 0:
            card(d, 190, 232, 1090, 350, a * (1 - kp), r=18, op=238)
            text(d, (640, 300), "見えない間合いを、見えるように。", F(GOTH_B, 52), INK, anchor="ms", alpha=a)
            seg(d, (330, 330), (330 + 620 * ease((t - t_vis) / 0.6), 330), 1, CYAN, 6, alpha=a)
            text(d, (640, 392), "MAAI（間合い）", F(GOTH_B, 34), CYAN, anchor="ms", alpha=cl((t - t_end - 0.4) / 0.5))
            a2 = cl((t - t_end - 0.9) / 0.5)
            text(d, (640, 560), "データはすべて合成です。実在の事業者・設備・図面は含みません。", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a2)
            if credit:
                text(d, (640, 596), f"読み上げ {credit}", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a2)
            text(d, (640, 632 if credit else 600), "github.com/Daxion1578/Minimum-Approach-Area-Indicator", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a2)

        caption(d, "C10", t, True, skip=(0, 1, 3))   # 字幕が出るのは 2 の文だけ。地が明るい地から 3D に替わる途中で形を変えない
        return flatten(f, ov)

    return scene
