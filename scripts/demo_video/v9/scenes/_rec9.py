"""v9 の C5〜C8（新しい画面の録画）の共通部品。

録画 assets/rec/rec9.webm と、record9.py が残した区切りと押した所・時刻（assets/rec/segments9.json の segments・marks）から、
語りの文（cue）ごとに「録画のどこを、どの速さで、どこへ寄って見せるか」を決める。描くのは compose9 の rec_cut（窓・寄り・波紋・字幕）。
録画を撮り直しても、marks の名前が同じなら、ここは直さずに付いてくる。

beat（語りの 1 文に当てる場面）: (カットの秒の始め, 終わり, [(録画の秒の始め, 終わり, 重み), ...], 寄る範囲の始め, 終わり)
重みは、その文の長さを録画の切れ端に配る割合。待ちの所は重みを小さくすると速く流れ、2.2 倍を超えると「早送り」の札が付く。
"""
from __future__ import annotations

import json

W1, H1 = 1920, 1080   # 録画の画素


def around(r, pad=60, minw=720, maxw=1920):
    """要素の範囲 r（x0, y0, x1, y1）を余白つきで含む 16:9 の範囲（録画の外へはみ出さない）。"""
    x0, y0, x1, y1 = r
    w = max(minw, (x1 - x0) + 2 * pad, ((y1 - y0) + 2 * pad) * 16 / 9)
    w = min(w, maxw, W1)
    h = w * 9 / 16
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    X0 = min(max(0, cx - w / 2), W1 - w)
    Y0 = min(max(0, cy - h / 2), H1 - h)
    return (X0, Y0, X0 + w, Y0 + h)


def at_point(xy, w=900):
    return around((xy[0] - 1, xy[1] - 1, xy[0] + 1, xy[1] + 1), pad=0, minw=w)


def tighter(z, k=0.06):
    """寄る範囲を少しだけ狭める（静かな寄り）。"""
    x0, y0, x1, y1 = z
    dx, dy = (x1 - x0) * k / 2, (y1 - y0) * k / 2
    return (x0 + dx, y0 + dy, x1 - dx, y1 - dy)


class Marks:
    def __init__(self, data, seg_id):
        s = next(x for x in data["segments"] if x["id"] == seg_id)
        self.t0, self.t1 = s["start"], s["end"]
        self.m = [x for x in data.get("marks", []) if self.t0 - 1.0 <= x["t"] <= self.t1 + 1.0]

    def find(self, name, nth=0):
        hits = [x for x in self.m if x["name"] == name] or [x for x in self.m if x["name"].startswith(name)]
        return hits[nth] if len(hits) > nth else None

    def t(self, name, default=None, nth=0):
        x = self.find(name, nth)
        return x["t"] if x else default

    def xy(self, name, nth=0):
        x = self.find(name, nth)
        return x.get("xy") if x else None

    def rect(self, name, sel):
        x = self.find(name)
        return ((x or {}).get("rects") or {}).get(sel)

    def get(self, name, key):
        x = self.find(name)
        return (x or {}).get(key)


def make(G, act):
    REC = G["REC"]
    seg_path = REC / "segments9.json"
    if not (REC / "rec9.webm").exists() or not seg_path.exists():
        return G["SCENES"][act]          # 新しい録画がまだ無ければ v8 の場面のまま
    data = json.loads(seg_path.read_text(encoding="utf-8"))
    cue, FULL, rec_cut, src2t = G["cue"], G["FULL"], G["rec_cut"], G["src2t"]
    hl_box, inwin, card, text, tag, F = G["hl_box"], G["inwin"], G["card"], G["text"], G["tag"], G["F"]
    GOTH_B, GOTH_R = G["GOTH_B"], G["GOTH_R"]
    INK, SUBINK, RED, GREEN, CYAN, WHITE = G["INK"], G["SUBINK"], G["RED"], G["GREEN"], G["CYAN"], G["WHITE"]
    AMBER = G.get("AMBER", (226, 150, 20))
    cl, back, ease, seg, P, SS, K = G["cl"], G["back"], G["ease"], G["seg"], G["P"], G["SS"], G["K"]

    n_cues = len(G["PARS"][act]["cues"])

    def span(i, D):
        """i 番目の文に当てるカットの秒（前の文の終わり〜次の文の始め）。"""
        a = 0.0 if i == 0 else cue(act, i)[0] - 0.15
        b = D if i == n_cues - 1 else cue(act, i + 1)[0] - 0.15
        return a, b

    def build(beats, D):
        segs, zooms = [], []
        for a, b, pieces, z0, z1 in beats:
            a, b = max(0.0, a), min(D, b)
            if b - a < 0.05:
                continue
            pieces = [p for p in pieces if p[0] is not None and p[1] is not None and p[1] > p[0]]
            if not pieces:
                continue
            tot = sum(p[2] for p in pieces)
            t = a
            for r0, r1, w in pieces:
                dt = (b - a) * w / tot
                segs.append((t, t + dt, r0, r1))
                t += dt
            zooms += [(a + 0.001, z0), (b - 0.04, z1 or z0)]
        if not segs:
            return [(0, D, 0, D)], [(0, FULL)]
        segs[0] = (0.0,) + segs[0][1:]
        segs[-1] = (segs[-1][0], D, segs[-1][2], segs[-1][3])
        zooms.sort(key=lambda z: z[0])
        return segs, zooms

    def ripples_for(segs, M, names):
        out = []
        for nm in names:
            x = M.find(nm)
            if x and x.get("xy"):
                tt = src2t(segs, x["t"])
                if tt >= 0:
                    out.append((tt, tuple(x["xy"])))
        return out

    plans = {}

    # ------------------------------------------------------------------ C5 STEP 1 図面を読む
    def plan_c5(D):
        M = Marks(data, "c5")
        ti, ta, tq, te = M.t("click #btnIngest"), M.t("s2_answer"), M.t("s2_questions"), M.t("c5_end")
        ans = M.rect("c5_end", "#hudAnswer") or M.rect("s2_answer", "#hudAnswer") or (1460, 30, 1900, 330)   # 終わりの板には「機器の一致」も出る
        drw = M.rect("s2_questions", "#hudDrawer") or (0, 0, 520, 1080)
        beats = []
        a, b = span(0, D)
        beats.append((a, b, [(ti - 1.0, ti + 1.0, 1.3), (ti + 1.0, ta - 0.3, 0.7)], FULL, FULL))
        a, b = span(1, D)
        beats.append((a, b, [(te - 2.4, te, 1)], FULL, tighter(FULL, 0.10)))
        a, b = span(2, D)
        beats.append((a, (a + b) / 2, [(te - 2.2, te, 1)], around(ans, 50, 760), None))
        drw_top = (drw[0], drw[1], drw[2], drw[1] + 560)
        beats.append(((a + b) / 2, b, [(tq + 0.2, tq + 3.8, 1)], around(drw_top, 20, 760), None))
        segs, zooms = build(beats, D)
        return segs, zooms, ripples_for(segs, M, ["click #btnIngest"]), {"ans": ans, "drw": drw_top}

    def over_c5(f, d, t, D, r):
        x = plans["C5"][3]
        a, b = span(2, D)
        hl_box(d, x["ans"], r, CYAN, inwin(None, t, a + 0.3, (a + b) / 2 - 0.1))
        hl_box(d, x["drw"], r, AMBER, inwin(None, t, (a + b) / 2 + 0.2, D), pad=-10)
        k = inwin(None, t, (a + b) / 2 + 0.4, D)
        if k > 0:   # Claude の役目: 今日の録画の実際の数（つながない回 15 件、つないだ回 6 件）
            x0, y0 = 720, 60
            card(d, x0, y0, x0 + 450, y0 + 196, k, outline=CYAN, r=16, op=246)
            text(d, (x0 + 24, y0 + 52), "Claude につなぐと", F(GOTH_R, 26), SUBINK, anchor="ls", alpha=k)
            text(d, (x0 + 24, y0 + 98), "確かめてほしいこと", F(GOTH_B, 30), INK, anchor="ls", alpha=k)
            text(d, (x0 + 24, y0 + 168), "15 件", F(GOTH_B, 44), SUBINK, anchor="ls", alpha=k)
            w15 = d.textlength("15 件", font=F(GOTH_B, 44)) / SS / K
            text(d, (x0 + 36 + w15, y0 + 164), "→", F(GOTH_B, 40), SUBINK, anchor="ls", alpha=k)
            k6 = back((t - (a + b) / 2 - 0.9) / 0.45)
            if k6 > 0:
                text(d, (x0 + 92 + w15, y0 + 168), "6 件", F(GOTH_B, int(round(56 * (0.85 + 0.15 * cl(k6))))), CYAN, anchor="ls", alpha=k * cl(k6))
        return f

    # ------------------------------------------------------------------ C6 STEP 2 対象を選ぶ（依頼文 → Claude → 送る前の置き換え → 停止範囲）
    def plan_c6(D):
        M = Marks(data, "c6")
        tc, tr, tu, ts = M.t("click #btnIntake"), M.t("s2b_intake"), M.t("click #btnIntakeUse"), M.t("c6_steps")
        tm, tg, te = M.t("c6_mask"), M.t("c6_green"), M.t("c6_end")
        drw = M.rect("s2b_intake", "#hudDrawer") or (0, 0, 520, 1080)
        ans = M.rect("c6_steps", "#hudAnswer") or (1460, 30, 1900, 200)
        tgt = M.rect("c6_green", '.mk[data-id="220-L1-CB"]')
        beats = []
        a, b = span(0, D)
        top = (drw[0], drw[1], drw[2], drw[1] + 600)
        beats.append((a, b, [(tc - 2.6, tc + 0.6, 1.5), (tc + 0.6, tr, 0.5), (tr, tr + 2.2, 1.1)], around(top, 10, 760), None))
        a, b = span(1, D)
        beats.append((a, b, [(tm + 0.2, tm + 4.0, 1)], FULL, tighter(FULL, 0.05)))
        a, b = span(2, D)
        beats.append((a, b, [(tu - 0.4, tu + 0.8, 1.0), (ts - 0.2, ts + 1.8, 1.4)], FULL, around(ans, 80, 900)))
        a, b = span(3, D)
        z = around(tgt, 260, 900) if tgt else FULL
        beats.append((a, b, [(tg - 1.6, te, 1)], z, tighter(z, 0.06)))
        segs, zooms = build(beats, D)
        return segs, zooms, ripples_for(segs, M, ["click #btnIntake", "click #btnIntakeUse"]), {
            "words": M.get("c6_mask_words", "words") or {}, "ans": ans, "tgt": tgt}

    def over_c6(f, d, t, D, r):
        x = plans["C6"][3]
        a, b = span(1, D)
        for k, v in x["words"].items():
            col = RED if k.startswith("before:") else GREEN
            t0 = a + (0.5 if col == RED else 1.3)
            hl_box(d, v, r, col, inwin(None, t, t0, b - 0.2), pad=4)
        a, b = span(2, D)
        hl_box(d, x["ans"], r, CYAN, inwin(None, t, (a + b) / 2, b - 0.15))
        a, b = span(3, D)
        k = inwin(None, t, a + 0.4, D)
        if k > 0:   # 相手端の条件（送電線ごと止める）
            card(d, 760, 30, 1170, 150, k, outline=GREEN, r=14, op=246)
            text(d, (784, 78), "送電線（東線1L）は", F(GOTH_R, 26), SUBINK, anchor="ls", alpha=k)
            text(d, (784, 128), "相手端も切る", F(GOTH_B, 40), INK, anchor="ls", alpha=k)
        return f

    # ------------------------------------------------------------------ C7 STEP 3 置場と重さ（→ クレーンは自動）
    def plan_c7(D):
        M = Marks(data, "c7")
        tt, tl, tb, tv = M.t("s4_top"), M.t("mouse laydown"), M.t("s4_box"), M.t("s4_verdict")
        tcr, tcd, tmv, trt = M.t("mouse crane"), M.t("s4_card"), M.t("s4_moved"), M.t("s4_rotated")
        tbk, trs, tus = M.t("s4_back"), M.t("c7_reason"), M.t("c7_unstoppable")
        side = M.rect("s4_box", "#hudSide") or (0, 120, 400, 800)
        ans = M.rect("s4_verdict", "#hudAnswer") or (1460, 30, 1900, 200)
        sel = M.rect("c7_reason", "#selectBox") or M.rect("c7_reason", "#hudDrawer") or (0, 0, 520, 1080)
        sel2 = M.rect("c7_unstoppable", "#selectBox") or sel
        lay = M.xy("mouse laydown") or (900, 600)
        crn = M.xy("mouse crane") or lay
        tmv = tmv or tcd
        beats = []
        a, b = span(0, D)
        beats.append((a, b, [(tt - 0.3, tl + 1.8, 1.2), (tb, tb + 2.0, 1)], FULL, around((side[0], side[1], lay[0] + 200, lay[1] + 200), 40, 1100)))
        a, b = span(1, D)
        beats.append((a, b, [(tv - 1.0, tv + 1.6, 1)], FULL, around(ans, 120, 1100)))
        a, b = span(2, D)
        beats.append((a, b, [(trs - 0.2, trs + 2.4, 1)], around(sel, 20, 760), None))
        a, b = span(3, D)
        zc = at_point(crn, 1000)
        beats.append((a, b, [(tv + 1.4, tv + 3.6, 1)], zc, tighter(zc, 0.08)))
        a, b = span(4, D)
        beats.append((a, b, [(tcr - 0.4, tcd + 0.8, 0.8), (tmv - 2.6, tmv + 0.6, 1.2)] + ([(trt - 1.6, trt, 0.6)] if trt else []), zc, None))
        a, b = span(5, D)
        beats.append((a, b, [(tus - 0.3, tus + 2.6, 1)], around(sel2, 20, 760), None))
        a, b = span(6, D)
        beats.append((a, b, [(tbk - 1.2, tbk + 1.2, 1)], FULL, tighter(FULL, 0.05)))
        segs, zooms = build(beats, D)
        return segs, zooms, ripples_for(segs, M, ["mouse laydown", "mouse crane"]), {"sel": sel, "sel2": sel2}

    def over_c7(f, d, t, D, r):
        x = plans["C7"][3]
        a1, b1 = span(1, D)
        k = inwin(None, t, a1 + 0.2, b1 - 0.1)
        if k > 0:   # 左に大きな数字: 10 t を吊る → 100t 級
            card(d, 110, 40, 480, 296, k, op=236)
            k2 = back((t - a1 - 0.9) / 0.5)
            text(d, (134, 92), "吊る機器", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=k)
            text(d, (134, 150), "10 t", F(GOTH_B, 52), INK, anchor="ls", alpha=k)
            if k2 > 0:
                text(d, (134, 202), "要るクレーン", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=k * cl(k2))
                text(d, (134 + (1 - k2) * 20, 272), "100t 級", F(GOTH_B, 64), CYAN, anchor="ls", alpha=k * cl(k2))
        a2, b2 = span(2, D)
        k = inwin(None, t, a2 + 0.2, b2 - 0.1)
        if k > 0:   # 重さだけなら 25t 級。でも母線に近づく
            x0, y0 = 740, 110
            card(d, x0, y0, x0 + 430, y0 + 262, k, outline=RED, r=16, op=246)
            text(d, (x0 + 24, y0 + 60), "25t 級", F(GOTH_B, 44), INK, anchor="ls", alpha=k)
            text(d, (x0 + 24, y0 + 104), "届くが、220kV 母線に", F(GOTH_R, 26), SUBINK, anchor="ls", alpha=k)
            text(d, (x0 + 24, y0 + 168), "5.37 m", F(GOTH_B, 54), RED, anchor="ls", alpha=k)
            nw = d.textlength("5.37 m", font=F(GOTH_B, 54)) / SS / K
            text(d, (x0 + 24 + nw + 12, y0 + 166), "まで近づく", F(GOTH_R, 26), INK, anchor="ls", alpha=k)
            text(d, (x0 + 24, y0 + 228), "必要は 7.00 m", F(GOTH_B, 28), INK, anchor="ls", alpha=k)
            if t > a2 + 1.4:
                fw = d.textlength("25t 級", font=F(GOTH_B, 44)) / SS / K
                seg(d, (x0 + 20, y0 + 46), (x0 + 28 + fw, y0 + 46), ease((t - a2 - 1.4) / 0.35), RED, 5, alpha=k)
        a3, b3 = span(3, D)
        k = inwin(None, t, a3 + 0.3, b3 - 0.1)
        if k > 0:
            tag(d, (640, 590), "緑のマス ＝ 据えてよい所（3 m 角）", 26, fg=WHITE, bg_=GREEN, alpha=k, anchor="ms")
        a5, b5 = span(5, D)
        hl_box(d, x["sel2"], r, AMBER, inwin(None, t, a5 + 0.4, b5 - 0.1), pad=-10)
        k = inwin(None, t, a5 + 0.6, b5 - 0.1)
        if k > 0:   # engine の with_outage の note と同じ中身
            x0, y0 = 650, 70
            card(d, x0, y0, x0 + 520, y0 + 222, k, outline=CYAN, r=16, op=246)
            text(d, (x0 + 24, y0 + 54), "220kV 母線 A 区間を止められるなら", F(GOTH_R, 26), SUBINK, anchor="ls", alpha=k)
            k2 = back((t - a5 - 1.0) / 0.45)
            if k2 > 0:
                text(d, (x0 + 24 + (1 - k2) * 16, y0 + 128), "25t 級で済む", F(GOTH_B, 54), CYAN, anchor="ls", alpha=k * cl(k2))
            text(d, (x0 + 24, y0 + 190), "止めるかどうかは、人が決める", F(GOTH_B, 28), INK, anchor="ls", alpha=k * cl((t - a5 - 1.6) / 0.3))
        return f

    # ------------------------------------------------------------------ C8 STEP 4 確認して承認
    def plan_c8(D):
        M = Marks(data, "c8")
        tn, tap, tp1, tp2, ttl = M.t("click #hudNext"), M.t("s5_approved"), M.t("c8_pdf_sld"), M.t("c8_pdf_crane"), M.t("c8_tiles")
        apr = M.rect("s5_approved", "#hudAnswer") or M.rect("s5_approved", "#approveBox") or (1460, 30, 1900, 330)
        beats = []
        a, b = span(0, D)
        beats.append((a, b, [(tn - 1.4, tap + 0.6, 1)], FULL, around(apr, 120, 1000)))
        a, b = span(1, D)
        beats.append((a, b, [(tp1 + 0.4, tp1 + 3.8, 1), (tp2 + 0.4, tp2 + 4.2, 1)], FULL, None))
        a, b = span(2, D)
        beats.append((a, b, [(ttl - 0.6, ttl + 2.0, 1)], FULL, tighter(FULL, 0.06)))
        segs, zooms = build(beats, D)
        return segs, zooms, ripples_for(segs, M, ["click #hudNext"]), {}

    def over_c8(f, d, t, D, r):
        a, b = span(2, D)
        k = back((t - a - 0.3) / 0.5)
        if k > 0:
            al = cl((t - a - 0.3) / 0.2)
            cx, cy = 1040, 110
            rr = 50 * (0.6 + 0.4 * k)
            d.ellipse([P(cx - rr), P(cy - rr), P(cx + rr), P(cy + rr)], fill=GREEN + (int(240 * al),))
            d.line([(P(cx - 22), P(cy + 2)), (P(cx - 6), P(cy + 18)), (P(cx + 24), P(cy - 16))], fill=(255, 255, 255, int(255 * al)), width=int(P(9)), joint="curve")
            tag(d, (cx - 120, cy + 88), "申請の図が そろった", 26, fg=WHITE, bg_=GREEN, alpha=al)
        return f

    table = {"C5": (plan_c5, over_c5, (1, "図面を読む")), "C6": (plan_c6, over_c6, (2, "対象を選ぶ")),
             "C7": (plan_c7, over_c7, (3, "置場と重さ")), "C8": (plan_c8, over_c8, (4, "確認して承認"))}
    plan, over, step = table[act]

    plans[act] = plan(G["ACT"][act]["dur"])   # 先に決めておく（mix_audio が波紋の時刻でクリックの音を鳴らす）
    G["PLANS"][act] = plans[act][:3]

    def fn(t, D):
        segs, zooms, ripples, _ = plans[act]
        return rec_cut(act, t, D, segs, zooms, step, ripples, over)
    return fn
