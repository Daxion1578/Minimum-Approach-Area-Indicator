"""v9 の C5〜C8（新しい画面の録画）の共通部品。

録画 assets/rec/rec9.webm と、record9.py が残した区切りと押した所・時刻（assets/rec/segments9.json の segments・marks）から、
語りの文（cue）ごとに「録画のどこを、どの速さで、どこへ寄って見せるか」を決める。描くのは compose9 の rec_cut（窓・寄り・波紋・字幕）。
録画を撮り直しても、marks の名前が同じなら、ここは直さずに付いてくる（ただし画面の中の文の位置は、いまの録画で測った値）。

beat（語りの 1 文に当てる場面）: (カットの秒の始め, 終わり, [(録画の秒の始め, 終わり, 重み), ...], 寄る範囲の始め, 終わり)
重みは、その文の長さを録画の切れ端に配る割合。待ちの所は重みを小さくすると速く流れ、2.2 倍を超えると「早送り」の札が付く。
指し方: 1 度に指すのは 1 か所だけ（橙の矢印か枠）。字が小さい所は寄る。問いへの答えは C1 の問いの札と同じ形で出す。
"""
from __future__ import annotations

import json
import math

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
    BLUE = G.get("BLUE", (40, 88, 160))
    cl, back, ease, seg, P, SS, K = G["cl"], G["back"], G["ease"], G["seg"], G["P"], G["SS"], G["K"]
    lerp, to_screen, REC_BOX = G["lerp"], G["to_screen"], G["REC_BOX"]

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

    # ------------------------------------------------------------------ 指す・答える（4 カット共通）
    def arrow(d, tip, tail, alpha=1.0, col=AMBER, w=8, head=26):
        """橙の矢印。白い縁つきで、暗い画面の上でも白い図面の上でも見える。"""
        if alpha <= 0.02:
            return
        (tx, ty), (sx, sy) = tip, tail
        L = math.hypot(tx - sx, ty - sy) or 1.0
        ux, uy = (tx - sx) / L, (ty - sy) / L
        nx, ny = -uy, ux
        bx, by = tx - ux * head, ty - uy * head
        hw = head * 0.62
        for c, ww, e in (((255, 255, 255), w + 6, 3.5), (col, w, 0.0)):
            fill = c + (int((235 if e else 255) * alpha),)
            d.line([(P(sx - ux * e), P(sy - uy * e)), (P(bx), P(by))], fill=fill, width=int(P(ww)))
            d.polygon([(P(tx + ux * e * 1.6), P(ty + uy * e * 1.6)),
                       (P(bx + nx * (hw + e) - ux * e), P(by + ny * (hw + e) - uy * e)),
                       (P(bx - nx * (hw + e) - ux * e), P(by - ny * (hw + e) - uy * e))], fill=fill)

    def point_at(d, t, t0, t1, r, pt, frm=(1, 0), length=120, gap=10):
        """録画の点 pt（元の画素）を、frm の向き（(1, 0) は右から、(-1, 0) は左から）から橙の矢印で指す。"""
        k = inwin(None, t, t0, t1, 0.2)
        if k <= 0:
            return
        q = to_screen(pt, r, REC_BOX)
        if not (REC_BOX[0] < q[0] < REC_BOX[0] + REC_BOX[2] and REC_BOX[1] < q[1] < REC_BOX[1] + REC_BOX[3]):
            return
        off = gap + 26 * (1 - ease((t - t0) / 0.3)) + 4 * math.sin((t - t0) * 2 * math.pi * 1.2)
        tip = (q[0] + frm[0] * off, q[1] + frm[1] * off)
        arrow(d, tip, (tip[0] + frm[0] * length, tip[1] + frm[1] * length), k)

    def answer(d, t, t0, s, i):
        """C1 の問いの札（i=0 止める範囲、i=1 クレーン）と同じ所・同じ形で出す答え。右から滑り込む。"""
        a = cl((t - t0) / 0.2)
        if a <= 0:
            return
        k = back((t - t0) / 0.5)
        y = 452 + 100 * i
        x0 = lerp(1300, 712, k)
        d.rounded_rectangle([P(x0 + 3), P(y - 62), P(x0 + 523), P(y + 24)], int(P(16)), fill=(0, 0, 0, int(60 * a)))
        card(d, x0, y - 66, x0 + 520, y + 20, a, outline=(176, 188, 202), r=16, op=248)
        d.rounded_rectangle([P(x0), P(y - 66), P(x0 + 10), P(y + 20)], int(P(4)), fill=(RED if i == 0 else BLUE) + (int(255 * a),))
        f = F(GOTH_B, 42)
        tw = d.textlength(s, font=f) / SS / K
        text(d, (x0 + 34, y), s, f, INK, anchor="ls", alpha=a * cl((1274 - (x0 + 34 + tw)) / 40))

    plans = {}

    # ------------------------------------------------------------------ C5 STEP 1 図面を読む（3 文）
    def plan_c5(D):
        M = Marks(data, "c5")
        ti, ta, tq, te = M.t("click #btnIngest"), M.t("s2_answer"), M.t("s2_questions"), M.t("c5_end")
        ans0 = M.rect("s2_answer", "#hudAnswer") or (1532, 52, 1892, 209)
        ans = M.rect("c5_end", "#hudAnswer") or (1532, 52, 1892, 336)   # 終わりの板には「機器の一致」も出る
        drw = M.rect("s2_questions", "#hudDrawer") or (0, 0, 520, 1080)
        drw_top = (drw[0], drw[1], drw[2], drw[1] + 560)
        match = (ans[0] + 14, ans[1] + 150, ans[2] - 26, ans[1] + 178)   # 「機器の一致: 結線図 147 台／平面図 147 台 — 一致」の行
        beats = []
        a, b = span(0, D)      # 図面から一つの立体にする
        beats.append((a, b, [(ti - 1.0, ti + 1.0, 1.3), (ti + 1.0, ta - 0.3, 0.7)], FULL, FULL))
        a, b = span(1, D)      # 記号の意味は Claude が読み、確かめることは 15 件から 5 件に（答えの板 → 問いの一覧）
        m = a + (b - a) * 0.4
        beats.append((a, m, [(ta - 0.1, ta + 2.3, 1)], around(ans0, 40, 700), None))
        beats.append((m, b, [(tq + 0.2, tq + 3.6, 1)], around(drw_top, 20, 760), None))
        a, b = span(2, D)      # 二つの図面で機器がそろっているか（引き出しを閉じた後の答えの板）
        za = around(ans, 30, 700)
        beats.append((a, b, [(te - 0.2, te + 3.6, 1)], za, tighter(za, 0.05)))
        segs, zooms = build(beats, D)
        return segs, zooms, ripples_for(segs, M, ["click #btnIngest"]), {"ans0": ans0, "drw": drw_top, "match": match, "m": m}

    def over_c5(f, d, t, D, r):
        x = plans["C5"][3]
        a, b = span(1, D)
        m = x["m"]
        hl_box(d, x["ans0"], r, CYAN, inwin(None, t, a + 0.3, m - 0.1))
        hl_box(d, x["drw"], r, AMBER, inwin(None, t, m + 0.2, b - 0.1), pad=-10)
        k = inwin(None, t, m + 0.3, b - 0.05)
        if k > 0:   # Claude の役目: 今日の録画の実際の数（つながない回 15 件、つないだ回 5 件。録り直したら画面の数に合わせる）
            x0, y0 = 720, 60
            card(d, x0, y0, x0 + 450, y0 + 196, k, outline=CYAN, r=16, op=246)
            text(d, (x0 + 24, y0 + 52), "Claude につなぐと", F(GOTH_R, 26), SUBINK, anchor="ls", alpha=k)
            text(d, (x0 + 24, y0 + 98), "確かめてほしいこと", F(GOTH_B, 30), INK, anchor="ls", alpha=k)
            text(d, (x0 + 24, y0 + 168), "15 件", F(GOTH_B, 44), SUBINK, anchor="ls", alpha=k)
            w15 = d.textlength("15 件", font=F(GOTH_B, 44)) / SS / K
            text(d, (x0 + 36 + w15, y0 + 164), "→", F(GOTH_B, 40), SUBINK, anchor="ls", alpha=k)
            k6 = back((t - m - 1.2) / 0.45)
            if k6 > 0:
                text(d, (x0 + 92 + w15, y0 + 168), "5 件", F(GOTH_B, int(round(56 * (0.85 + 0.15 * cl(k6))))), CYAN, anchor="ls", alpha=k * cl(k6))
        a, b = span(2, D)
        mt = x["match"]
        hl_box(d, mt, r, AMBER, inwin(None, t, a + 0.5, D + 1), pad=6)
        point_at(d, t, a + 0.5, D + 1, r, (mt[0] - 6, (mt[1] + mt[3]) / 2), frm=(-1, 0))
        return f

    # ------------------------------------------------------------------ C6 STEP 2 対象を選ぶ（5 文: 依頼文 → 置き換え → 人が入れる → 切る開閉器 → 相手端）
    def plan_c6(D):
        M = Marks(data, "c6")
        tc, tr, tu, ts = M.t("click #btnIntake"), M.t("s2b_intake"), M.t("click #btnIntakeUse"), M.t("c6_steps")
        tm, tg = M.t("c6_mask"), M.t("c6_green")
        ans = M.rect("c6_steps", "#hudAnswer") or (1552, 52, 1892, 159)
        tgt = M.rect("c6_green", '.mk[data-id="220-L1-CB"]')
        req, btn = (16, 216, 400, 301), (16, 312, 157, 349)   # 依頼文の欄と「Claude で読み取る」（いまの録画の 148〜167 秒の引き出しで測った）
        use = (28, 625, 186, 665)                              # 「この内容で入れる」（引き出しが下へ送られた後、168〜171 秒）
        box2 = (16, 253, 403, 677)                             # 読み取った 4 つ（原文の引用つき）とボタン
        beats = []
        a, b = span(0, D)      # 依頼文を貼ると、Claude が読み取る（Claude の待ちは早送り）
        beats.append((a, b, [(tc - 2.6, tc + 0.6, 1.8), (tc + 0.6, tr, 0.5), (tr, tr + 2.2, 0.8)], around((0, 190, 420, 360), 10, 680), None))
        a, b = span(1, D)      # 仮の名前に置き換えてから送る（赤 → 緑）
        beats.append((a, b, [(tm + 1.0, tm + 4.8, 1)], around((150, 100, 1770, 800), 10, 1640), (125, 187, 1025, 693)))
        a, b = span(2, D)      # 人が原文と並べて確かめ、入れる
        beats.append((a, b, [(tu - 2.9, tu + 0.7, 1)], around(box2, 6, 700), None))
        a, b = span(3, D)      # 切る開閉器は、計算で出る（答えの板「停止範囲ができた 切る開閉器 3」）
        za = around(ans, 40, 640)
        beats.append((a, a + 0.8, [(ts - 0.2, ts + 0.6, 1)], FULL, za))
        beats.append((a + 0.8, b, [(ts + 0.6, ts + 2.4, 1)], za, tighter(za, 0.04)))
        a, b = span(4, D)      # 送電線は、向こうの変電所でも止めてもらう（結線図の 20E1-110 のあたり）
        z = around(tgt, 260, 900) if tgt else FULL
        beats.append((a, b, [(tg - 0.4, tg + 4.2, 1)], z, tighter(z, 0.06)))
        segs, zooms = build(beats, D)
        return segs, zooms, ripples_for(segs, M, ["click #btnIntake", "click #btnIntakeUse"]), {
            "words": M.get("c6_mask_words", "words") or {}, "ans": ans, "req": req, "btn": btn, "use": use,
            "tclick": src2t(segs, tc), "tuse": src2t(segs, tu)}

    def over_c6(f, d, t, D, r):
        x = plans["C6"][3]
        a, b = span(0, D)
        tk = x["tclick"]
        if tk > 0:   # 依頼文の欄 → 押す前に「Claude で読み取る」へ矢印が移る
            u = ease((t - (tk - 0.9)) / 0.45)
            rq, bt = x["req"], x["btn"]
            p = (lerp(rq[2], bt[2], u), lerp((rq[1] + rq[3]) / 2, (bt[1] + bt[3]) / 2, u))
            point_at(d, t, a + 0.15, tk + 0.4, r, p, frm=(1, 0))
        a, b = span(1, D)
        for k, v in x["words"].items():
            col = RED if k.startswith("before:") else GREEN
            t0 = a + (0.5 if col == RED else 1.3)
            hl_box(d, v, r, col, inwin(None, t, t0, b - 0.2), pad=4)
        a, b = span(2, D)
        if x["tuse"] > 0:
            u = x["use"]
            point_at(d, t, a + 0.4, x["tuse"] + 0.35, r, (u[2], (u[1] + u[3]) / 2), frm=(1, 0))
        a, b = span(3, D)
        hl_box(d, x["ans"], r, CYAN, inwin(None, t, a + 0.6, b - 0.15))
        a, b = span(4, D)
        k = inwin(None, t, a + 0.4, D + 1)
        if k > 0:   # 相手端の条件（送電線は向こうの変電所でも切る）
            card(d, 700, 30, 1150, 164, k, outline=GREEN, r=14, op=248)
            text(d, (726, 86), "向こうの変電所でも", F(GOTH_B, 36), INK, anchor="ls", alpha=k)
            text(d, (726, 140), "止めてもらう（相手端）", F(GOTH_B, 36), INK, anchor="ls", alpha=k)
        answer(d, t, D - 2.0, "止めるのは、ここまで", 0)
        return f

    # ------------------------------------------------------------------ C7 STEP 3 置場と重さ（7 文: 25t で足りる → 近すぎる → 止めれば 25t → 止められない → Claude が読んだ条件 → 100t 級）
    def plan_c7(D):
        M, M6 = Marks(data, "c7"), Marks(data, "c6")
        tt, tl, tb, tv = M.t("s4_top"), M.t("mouse laydown"), M.t("s4_box"), M.t("s4_verdict")
        tcd, tmv = M.t("s4_card"), M.t("s4_moved")
        trs, tus = M.t("c7_reason"), M.t("c7_unstoppable")
        tr6 = M6.t("s2b_intake")
        side = M.rect("s4_box", "#hudSide") or (0, 120, 400, 800)
        sel2 = M.rect("c7_unstoppable", "#selectBox") or (16, 164, 403, 631)
        lay = M.xy("mouse laydown") or (900, 600)
        tmv = tmv or tcd
        why = (20, 118, 400, 178)       # 引き出しの「重さと届く距離だけなら 25t 級…」（c7_reason の時の位置）
        nostop = (20, 525, 400, 600)    # 引き出しの「止められない設備（依頼文）…止められるなら 25t 級で済む」（c7_unstoppable）
        line6 = (20, 416, 330, 442)     # STEP 2 の読み取り「止められない設備: 220kV 母線 A区間」（s2b_intake、引き出しが送られる前）
        beats = []
        a, b = span(0, D)      # 平面図で置き場を決め、重さを入れる
        beats.append((a, b, [(tt + 1.0, tl + 0.8, 1.4), (tb, tb + 2.0, 0.8)], FULL, around((side[0], side[1], lay[0] + 200, lay[1] + 200), 40, 1100)))
        a, b = span(1, D)      # 重さだけなら 25t 級で足りる（引き出しの理由の文へ寄る）
        beats.append((a, b, [(trs + 0.1, trs + 2.9, 1)], around(why, 10, 780), around(why, 10, 620)))
        a, b = span(2, D)      # どこに据えても近づきすぎる（比べの札。下地はクレーンを動かす所）
        beats.append((a, b, [(tmv - 2.6, tmv + 0.8, 1)], FULL, None))
        a, b = span(3, D)      # 母線を止められれば 25t 級（引き出しが「止められない設備」へ送られる所）
        zs = around(sel2, 10, 760)
        beats.append((a, b, [(trs + 2.9, tus - 0.1, 1)], zs, None))
        a, b = span(4, D)      # 依頼文には、止められない、とある
        beats.append((a, b, [(tus - 0.1, tus + 3.4, 1)], zs, around(nostop, 10, 640)))
        a, b = span(5, D)      # Claude が読み、人が確かめた条件（STEP 2 の読み取りをもう一度）
        zl = around((16, 357, 403, 560), 10, 700)
        beats.append((a, b, [(tr6 + 0.4, tr6 + 3.9, 1)], zl, tighter(zl, 0.04)))
        a, b = span(6, D)      # だから 100t 級（判定の画面）
        beats.append((a, b, [(tv - 0.3, tv + 3.6, 1)], FULL, tighter(FULL, 0.05)))
        segs, zooms = build(beats, D)
        return segs, zooms, ripples_for(segs, M, ["mouse laydown"]), {"why": why, "nostop": nostop, "line6": line6}

    def over_c7(f, d, t, D, r):
        x = plans["C7"][3]
        a, b = span(1, D)
        w = x["why"]
        point_at(d, t, a + 0.4, b - 0.1, r, (w[2], (w[1] + w[3]) / 2), frm=(1, 0))
        a, b = span(2, D)
        k = inwin(None, t, a + 0.35, b - 0.1)
        if k > 0:   # 比べの札: 一番近い充電部（220kV 母線）まで。25t 級は必要な離れに届かず、100t 級は届く（engine の値と同じ）
            card(d, 120, 48, 1160, 592, k, r=18, op=250)
            text(d, (160, 112), "220kV 母線まで、いちばん近づく距離", F(GOTH_B, 32), INK, anchor="ls", alpha=k)
            x0b, pxm = 360, 66
            for lab, v, s, col, dt, yc in (("25t 級", 5.37, "5.37 m ×", RED, 0.7, 230), ("100t 級", 8.08, "8.08 m ○", GREEN, 1.6, 350)):
                kr = cl((t - a - dt) / 0.25) * k
                if kr <= 0:
                    continue
                text(d, (160, yc + 15), lab, F(GOTH_B, 40), INK, anchor="ls", alpha=kr)
                g = ease((t - a - dt) / 0.5)
                solid = tuple(int(255 + (c - 255) * 0.88) for c in col)   # 透かさない（重ねた所の画素は置き換わるので、薄めた色で塗る）
                d.rounded_rectangle([P(x0b), P(yc - 26), P(x0b + max(4, v * pxm * g)), P(yc + 26)], int(P(6)), fill=solid + (int(255 * kr),))
                text(d, (930, yc + 15), s, F(GOTH_B, 40), col, anchor="ls", alpha=kr * cl((t - a - dt - 0.45) / 0.25))
            kd = cl((t - a - 0.5) / 0.3) * k
            if kd > 0:   # 必要な離れの破線（棒の上に引く）
                xr, yy = x0b + 7.0 * pxm, 170
                while yy < 412:
                    d.line([(P(xr), P(yy)), (P(xr), P(min(yy + 12, 412)))], fill=INK + (int(230 * kd),), width=int(P(3)))
                    yy += 20
                text(d, (xr, 160), "必要 7.00 m", F(GOTH_B, 28), INK, anchor="ms", alpha=kd)
            text(d, (160, 556), "数字は例示値。実際は会社の決まりと機種の荷重表を入れる", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=k)
        a, b = span(3, D)
        k = inwin(None, t, a + 0.3, b - 0.1)
        if k > 0:   # 止められるかどうかで、答えが変わる
            card(d, 600, 96, 1190, 336, k, outline=CYAN, r=16, op=248)
            for lab, v, col, dt, yb in (("母線も止めれば", "25t 級", GREEN, 0.0, 186), ("依頼文どおり", "100t 級", CYAN, 1.2, 300)):
                kr = cl((t - a - 0.3 - dt) / 0.3) * k
                if kr <= 0:
                    continue
                text(d, (628, yb), lab, F(GOTH_B, 30), INK, anchor="ls", alpha=kr)
                text(d, (858, yb), "→", F(GOTH_B, 34), SUBINK, anchor="ls", alpha=kr)
                text(d, (912 + (1 - back((t - a - 0.3 - dt) / 0.45)) * 14, yb + 4), v, F(GOTH_B, 52), col, anchor="ls", alpha=kr)
            seg(d, (624, 238), (1166, 238), 1, (214, 222, 230), 2, alpha=k)
        a, b = span(4, D)
        n = x["nostop"]
        point_at(d, t, a + 0.5, b - 0.1, r, (n[2], n[1] + 16), frm=(1, 0))
        a, b = span(5, D)
        l6 = x["line6"]
        point_at(d, t, a + 0.3, b - 0.1, r, (l6[2], (l6[1] + l6[3]) / 2), frm=(1, 0))
        k = inwin(None, t, a + 1.0, b - 0.1)
        if k > 0:
            card(d, 700, 380, 1190, 540, k, outline=CYAN, r=16, op=248)
            text(d, (726, 446), "依頼文の一言で、", F(GOTH_B, 38), INK, anchor="ls", alpha=k)
            text(d, (726, 508), "計算の答えが変わる", F(GOTH_B, 38), CYAN, anchor="ls", alpha=k)
        a, b = span(6, D)
        k = inwin(None, t, a + 0.2, D + 1)
        if k > 0:   # 左に大きな数字: 10 t を吊る → 100t 級
            card(d, 110, 40, 480, 296, k, op=236)
            k2 = back((t - a - 0.9) / 0.5)
            text(d, (134, 92), "吊る機器", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=k)
            text(d, (134, 150), "10 t", F(GOTH_B, 52), INK, anchor="ls", alpha=k)
            if k2 > 0:
                text(d, (134, 202), "要るクレーン", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=k * cl(k2))
                text(d, (134 + (1 - k2) * 20, 272), "100t 級", F(GOTH_B, 64), CYAN, anchor="ls", alpha=k * cl(k2))
        answer(d, t, a + 1.6, "クレーンは、100t 級", 1)
        return f

    # ------------------------------------------------------------------ C8 STEP 4 確認して承認（4 文）
    def plan_c8(D):
        M = Marks(data, "c8")
        tn, tap, tp1, tp2, ttl = M.t("click #hudNext"), M.t("s5_approved"), M.t("c8_pdf_sld"), M.t("c8_pdf_crane"), M.t("c8_tiles")
        apr = M.rect("s5_approved", "#hudAnswer") or M.rect("s5_approved", "#approveBox") or (1460, 30, 1900, 330)
        bar = M.rect("s5_approved", "#hudBar") or (650, 863, 1270, 1058)
        btn = (1592, 992, 1888, 1052)          # 「この配置で OK（承認）」（いまの録画で測った）
        cond = (1046, 203, 1475, 238)          # クレーン配置の平面図の「承認の条件」（検電と接地・相手端）
        # PDF が画面に出ているのは、押してから少し後（いまの録画: 結線図 tp1+4.6〜+12.8 秒、平面図 tp2+4.5〜+8.6 秒）
        beats = []
        a, b = span(0, D)      # OK を押す（押すまでは寄らない）→ 承認済み
        m = a + 1.3
        beats.append((a, m, [(tn - 1.4, tn + 0.4, 1)], FULL, FULL))
        beats.append((m, b, [(tn + 0.4, tn + 4.2, 1)], FULL, around(apr, 120, 1000)))
        a, b = span(1, D)      # 停止範囲の結線図と、クレーン配置の平面図（2 秒ずつ）
        beats.append((a, b, [(tp1 + 5.0, tp1 + 7.0, 1), (tp2 + 4.8, tp2 + 6.6, 1)], FULL, None))
        a, b = span(2, D)      # 検電と接地、相手端の条件（平面図の条件の欄へ寄る）
        zc = around(cond, 10, 470)
        beats.append((a, a + 0.7, [(tp2 + 6.6, tp2 + 7.0, 1)], FULL, zc))
        beats.append((a + 0.7, b, [(tp2 + 7.0, tp2 + 8.4, 1)], zc, tighter(zc, 0.04)))
        a, b = span(3, D)      # これを添えて申請する（ステップ図の札）
        beats.append((a, b, [(ttl - 1.5, ttl + 2.5, 1)], FULL, around(bar, 60, 1100)))
        segs, zooms = build(beats, D)
        return segs, zooms, ripples_for(segs, M, ["click #hudNext"]), {"btn": btn, "cond": cond, "tclick": src2t(segs, tn)}

    def over_c8(f, d, t, D, r):
        x = plans["C8"][3]
        a, b = span(0, D)
        if x["tclick"] > 0:
            bt = x["btn"]
            point_at(d, t, a + 0.1, x["tclick"] + 0.3, r, (bt[0], (bt[1] + bt[3]) / 2), frm=(-1, 0))
        a, b = span(2, D)
        hl_box(d, x["cond"], r, AMBER, inwin(None, t, a + 0.7, b - 0.1), pad=6)
        a, b = span(3, D)
        k = back((t - a - 0.3) / 0.5)
        if k > 0:
            al = cl((t - a - 0.3) / 0.2)
            cx, cy = 1000, 110
            rr = 50 * (0.6 + 0.4 * k)
            d.ellipse([P(cx - rr), P(cy - rr), P(cx + rr), P(cy + rr)], fill=GREEN + (int(240 * al),))
            d.line([(P(cx - 22), P(cy + 2)), (P(cx - 6), P(cy + 18)), (P(cx + 24), P(cy - 16))], fill=(255, 255, 255, int(255 * al)), width=int(P(9)), joint="curve")
            tag(d, (cx, cy + 92), "申請に添える図が そろった", 26, fg=WHITE, bg_=GREEN, alpha=al, anchor="ms")
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
