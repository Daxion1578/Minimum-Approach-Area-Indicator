"""C4 間合い（v9）: 図面 3 枚が画面へ入る → 新しい画面の答えと根拠 → 名前 → 役割の分け方（読む Claude → 判定 計算 → 決める 人）。

画面写真は assets/rec9/s2_answer.png（220kV の見本、STEP 2 で自動配置した直後の 1920x1080）。
答えの板の位置は assets/rec9/s2_answer.json（撮るときに #hudAnswer の位置を書いた）。図面は今の合成図面（data/sites/SITE-01/drawings）から。
名前は kw("C4", "間合い") に出す（曲が明るくなる時刻と同じ）。
"""
from __future__ import annotations

import json

from PIL import ImageDraw


def make(G):
    HERE = G["HERE"]
    F, GOTH_B, GOTH_R = G["F"], G["GOTH_B"], G["GOTH_R"]
    text, tag, card, seg, caption, window = G["text"], G["tag"], G["card"], G["seg"], G["caption"], G["window"]
    new_ov, flatten, bg, img, fit_rect = G["new_ov"], G["flatten"], G["bg"], G["img"], G["fit_rect"]
    cl, back, lerp, ease, smooth = G["cl"], G["back"], G["lerp"], G["ease"], G["smooth"]
    INK, SUBINK, CYAN, GREEN, BLUE, RED, WHITE = G["INK"], G["SUBINK"], G["CYAN"], G["GREEN"], G["BLUE"], G["RED"], G["WHITE"]
    FULL, kw, cue = G["FULL"], G["kw"], G["cue"]

    R9 = HERE / "assets" / "rec9"
    shot_p = R9 / "s2_answer.png"
    SHOT = img(shot_p) if shot_p.exists() else G["SHOT_V"]
    # 答えの板（元の画素）。無ければ右上の目安
    ans = (1490, 62, 1880, 160)
    try:
        j = json.loads((R9 / "s2_answer.json").read_text(encoding="utf-8"))
        if j.get("answer"): ans = tuple(j["answer"])
    except (OSError, ValueError):
        pass

    # 今の図面（単線結線図・平面図・断面図）。無ければ v8 の図面
    TH = G["TH"]
    try:
        sld, lay = img(R9 / "d_sld-1.png"), img(R9 / "d_layout-1.png")
        TH = [("単線結線図", sld, fit_rect(1200, 300, 780, 340 / 210)),
              ("平面図", lay, fit_rect(1000, 720, 1300, 340 / 210)),
              ("断面図", lay, fit_rect(2390, 1090, 1250, 340 / 210))]
    except OSError:
        pass

    cues = G["PARS"]["C4"]["cues"]
    n = len(cues)
    i_mai = next((i for i, c in enumerate(cues) if c["text"].strip().rstrip("。") == "間合い"), min(1, n - 1))
    # 役割の分け方（台本 v9.3 の 3・4 文目）。文が足りなければ出さない
    c2 = cue("C4", 2)[0] if n > 2 else None
    c3 = cue("C4", 3)[0] if n > 3 else None
    ROLES = (("読む", "Claude", BLUE, ("依頼文と記号を読む",), "Claude"),
             ("判定", "計算", INK, ("停電・距離・クレーンの級", "同じ図面なら、同じ答え"), "計算"),
             ("決める", "人", GREEN, ("この内容で入れる", "この配置で OK"), "人"))

    def c4(t, D):
        f = bg(); ov = new_ov(); d = ImageDraw.Draw(ov)
        kt = kw("C4", "間合い", None)
        if kt is None:
            kt = cue("C4", i_mai)[0]
        cx, cy = 560, 248
        # 1) 左に縦に並んだ図面 3 枚（C3 の並び）が、画面の中へ入って消える
        for i, (name, src, rr) in enumerate(TH):
            k = smooth((t - 0.08 * i) / 0.9)
            if k >= 0.97: continue
            x = lerp(60, cx - 90, k); y = lerp(40 + 185 * i, cy - 50, k); s = lerp(0.82, 0.3, k)
            window(f, src, rr, (x, y, 340 * s, 210 * s), radius=10, alpha=1 - k)
            if k < 0.25:
                tag(d, (x + 8, y + 210 * s - 6), name, 24, alpha=1 - k / 0.25)
        # 2) 新しい画面（答えと根拠）が開く
        kw_ = back((t - 0.55) / 0.6); ko = smooth((t - kt + 0.5) / 0.4)
        if kw_ > 0 and ko < 1:
            w = lerp(220, 700, kw_); h = w * 9 / 16; yy = cy - 30 * ko
            bx_ = (cx - w / 2, yy - h / 2, w, h)
            window(f, SHOT, FULL, bx_, radius=14, alpha=(1 - ko) if ko > 0 else 1.0, shadow_on=ko <= 0)
            px = lambda sx, sy: (bx_[0] + sx / 1920 * w, bx_[1] + sy / 1080 * h)
            anchors = [px(ans[0] + 20, (ans[1] + ans[3]) / 2 - 18), px(ans[0] + 20, ans[3] - 10)]
            rows = (("答え", "100t 級で 可", "クレーンの級は例示値", CYAN), ("根拠", "最小離隔 8.08 m", "必要 7.00 m（例示値）", GREEN))
            for i, (lab, l1, l2, col) in enumerate(rows):
                a = cl((t - 1.1 - 0.35 * i) / 0.3) * (1 - ko)
                if a <= 0: continue
                y0 = 64 + 160 * i; x0 = 910
                card(d, x0, y0, x0 + 340, y0 + (104 if not l2 else 140), a, outline=col, r=14, op=250)
                tag(d, (x0 + 18, y0 + 42), lab, 24, fg=(255, 255, 255), bg_=col, alpha=a)
                text(d, (x0 + 20, y0 + 88), l1, F(GOTH_B, 32), INK, anchor="ls", alpha=a)
                if l2: text(d, (x0 + 20, y0 + 124), l2, F(GOTH_R, 26), SUBINK, anchor="ls", alpha=a)
                seg(d, (x0, y0 + 36), anchors[i], 1, col, 3, alpha=a)
        # 3) 名前（役割の図に移るとき、上へ小さく退く）
        u = smooth((t - c2 + 0.35) / 0.5) if c2 is not None else 0.0
        k = back((t - kt) / 0.55)
        if k > 0:
            a = cl((t - kt) / 0.2)
            size = (int(120 * lerp(0.7, 1.0, k)) if k < 1 else 120)
            size = int(lerp(size, 56, u))
            text(d, (640, lerp(352, 86, u)), "間合い", F(GOTH_B, size), INK, anchor="ms", alpha=a)
            if u < 1:
                seg(d, (470, 382), (470 + 340 * ease((t - kt - 0.2) / 0.5), 382), 1, CYAN, 8, alpha=1 - u)
                a2 = cl((t - kt - 0.4) / 0.4) * (1 - u)
                text(d, (640, 430), "MAAI  Minimum Approach Area Indicator", F(GOTH_B, 28), CYAN, anchor="ms", alpha=a2)
                text(d, (640, 488), "頭の中の立体を、図面から 3D と数字に", F(GOTH_B, 32), INK, anchor="ms", alpha=cl((t - kt - 0.7) / 0.4) * (1 - u))
        # 4) 役割の分け方: Claude には、判定させない
        if c2 is not None and t > c2 - 0.15:
            ah = cl((t - c2 + 0.15) / 0.3)
            text(d, (640, 152), "Claude には、判定させない", F(GOTH_B, 40), INK, anchor="ms", alpha=ah)
            for i, (lab, who, col, subs, word) in enumerate(ROLES):
                t_i = kw("C4", word, c2 + 0.9 * i)
                if t_i is None: t_i = c2 + 0.9 * i
                t_i = max(t_i - 0.25, c2 + 0.05)
                kb = back((t - t_i) / 0.45)
                if kb <= 0: continue
                ab = cl(kb)
                x = 170 + i * 330; y = lerp(222, 200, kb)
                card(d, x, y, x + 280, y + 150, ab, outline=col, r=20)
                tag(d, (x + 24, y + 48), lab, 26, fg=WHITE, bg_=col, alpha=ab)
                text(d, (x + 140, y + 118), who, F(GOTH_B, 52), col, anchor="ms", alpha=ab)
                if i < 2: text(d, (x + 305, y + 92), "→", F(GOTH_B, 40), SUBINK, anchor="ms", alpha=ab)
                asub = cl((t - t_i - 0.3) / 0.3)
                for j, sl in enumerate(subs):
                    text(d, (x + 140, 392 + 32 * j), sl, F(GOTH_R, 24), SUBINK, anchor="ms", alpha=asub)
        # 5) 判: CLAUDE.md の約束（11/02 の判断の記録）
        if c3 is not None and t > c3 - 0.1:
            ks = back((t - c3 + 0.1) / 0.4)
            if ks > 0:
                a = cl(ks)
                x0, y0 = 790 + (1 - min(1, ks)) * 18, 452
                card(d, x0, y0, x0 + 380, y0 + 84, a, outline=RED, r=12, op=246)
                d.rounded_rectangle([G["P"](x0 + 6), G["P"](y0 + 6), G["P"](x0 + 374), G["P"](y0 + 78)], int(G["P"](8)),
                                    outline=RED + (int(200 * a),), width=int(G["P"](2)))
                text(d, (x0 + 190, y0 + 40), "CLAUDE.md の約束", F(GOTH_B, 30), RED, anchor="ms", alpha=a)
                text(d, (x0 + 190, y0 + 70), "11/02 の判断の記録", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a)
        caption(d, "C4", t, False, skip=(i_mai,))
        return flatten(f, ov)

    return c4
