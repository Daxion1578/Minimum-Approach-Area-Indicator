"""C9 作り方（v9.3）。語り（self.txt の 9 段落目）の 4 文に合わせて順に出す。
0 Claude Code で作った（11/02〜11/08）と判断の記録の日付の並び → 1 作った人・覚えたコマンド 0 → 2 Skill・サブエージェント・フックの札
→ 3 動画の場面を 6 つのサブエージェントが同時に作った図と、前提を知らない 1 つが操作の流れを点検して穴を見つけ、直した図。
（読む Claude → 決める 計算 → 承認 人 の 3 つの箱は C4 へ移した）

compose9.py が make(G) を呼ぶ。G は compose9 の globals。
"""
from __future__ import annotations

TESTS = 107   # 2026-11-08 夕方にリポジトリ直下で MAAI_OFFLINE=1 python -m pytest -q（107 passed）

# docs/decisions.md の日付つきの行から短く（実在の名前・設備名は含まない）
DEC9 = [("11/02", "判定は計算、Claude は意味づけと提案"), ("11/03", "離隔表は「要確認」の印つきで置く"),
        ("11/04", "テストは常にオフラインで回す"), ("11/05", "離隔の既定値を公開資料と照合"),
        ("11/06", "変圧器の取り替えは専用ベイまで止める"), ("11/07", "Claude に送る文のマスクを広げた"),
        ("11/08", "操作を 4 段に絞った")]

# 11/08 に動画の場面を手分けしたサブエージェント（同時に 6 つ）
SIX = ["3D の静止画", "冒頭と役割", "見えない電気", "いまの決め方", "作り方と締め", "読み上げ"]


def make(G):
    ImageDraw = G["ImageDraw"]
    F, GOTH_B, GOTH_R, MONO = G["F"], G["GOTH_B"], G["GOTH_R"], G["MONO"]
    text, card, tag, bg, cue, caption, seg = G["text"], G["card"], G["tag"], G["bg"], G["cue"], G["caption"], G["seg"]
    new_ov, flatten, fit_text, P = G["new_ov"], G["flatten"], G["fit_text"], G["P"]
    cl, lerp, ease, back, smooth = G["cl"], G["lerp"], G["ease"], G["back"], G["smooth"]
    INK, SUBINK, WHITE, BLUE, GREEN, CYAN, RED = G["INK"], G["SUBINK"], G["WHITE"], G["BLUE"], G["GREEN"], G["CYAN"], G["RED"]
    AMBER = G.get("AMBER", (226, 150, 20))
    n = len(G["PARS"]["C9"]["cues"])

    def cs(i):   # i 番目の文の始まり（文が足りないときは最後の文に寄せる）
        return cue("C9", min(i, n - 1))[0]

    # 2 文目の札: 名前つき（Skill／サブエージェント／フック）
    TOOLS = [("Skill", ["/daily「朝」・/wrap「終わり」", "手順をまとめた Skill は、全部で 7 つ"], CYAN),
             ("サブエージェント", ["点検係＝Sonnet・タスク係＝Haiku", "11/08 は、動画の場面を 6 つ同時に"], GREEN),
             ("フック", ["commit・push の前に、公開安全チェック", f"engine を直したら、テスト（{TESTS} 件）"], AMBER)]

    def arrow_down(d, x, y0, y1, a, col=SUBINK):
        if a <= 0: return
        seg(d, (x, y0), (x, y1), 1, col, 4, alpha=a)
        d.polygon([(P(x - 10), P(y1 - 12)), (P(x + 10), P(y1 - 12)), (P(x), P(y1 + 2))], fill=col + (int(255 * a),))

    def scene(t, D):
        f = bg(); ov = new_ov(); d = ImageDraw.Draw(ov)
        a0, b0, c0, e0 = cs(0), cs(1), cs(2), cs(3)
        cols = 1 - smooth((t - e0 + 0.35) / 0.4)          # 左右の列は 4 文目で消して、図に替える

        if cols > 0:
            # ---- 左の列: Claude Code で作った（0）→ 作った人・覚えたコマンド 0（1）
            a = cl((t - a0 + 0.1) / 0.35) * cols
            text(d, (60, 96), "Claude Code", F(GOTH_B, 46), INK, anchor="ls", alpha=a)
            text(d, (62, 136), "で作った（11/02〜11/08）", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a)
            a1 = cl((t - b0) / 0.3) * cols
            if a1 > 0:
                tag(d, (60, 196), "作った人", 24, fg=WHITE, bg_=SUBINK, alpha=a1)
                text(d, (182, 192), "変電所の工事担当", F(GOTH_B, 26), INK, anchor="ls", alpha=a1)
                text(d, (62, 230), "ソフトの開発は、経験が浅い", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a1)
                a2 = cl((t - b0 - 0.9) / 0.3) * cols
                text(d, (60, 296), "覚えたコマンド", F(GOTH_B, 30), INK, anchor="ls", alpha=a2)
                text(d, (52, 468), "0", F(GOTH_B, int(round(170 * lerp(1.2, 1.0, ease((t - b0 - 0.9) / 0.4))))), CYAN, anchor="ls", alpha=a2)
                text(d, (196, 406), "言葉で", F(GOTH_B, 30), INK, anchor="ls", alpha=a2)
                text(d, (196, 448), "頼むだけ", F(GOTH_B, 30), INK, anchor="ls", alpha=a2)

            # ---- 右の列: 判断の記録（0〜1）→ Skill・サブエージェント・フック（2）
            out = smooth((t - c0 + 0.3) / 0.4)
            k = back((t - a0 - 0.3) / 0.5); a = cl((t - a0 - 0.3) / 0.25) * (1 - out) * cols
            if a > 0:
                x0 = 590 + lerp(80, 0, k) + 80 * out; y0 = 40
                card(d, x0, y0, x0 + 640, y0 + 520, a, outline=(200, 212, 224), r=16, op=250)
                text(d, (x0 + 26, y0 + 50), "docs/decisions.md", F(MONO, 26), BLUE, anchor="ls", alpha=a)
                text(d, (x0 + 290, y0 + 50), "判断の記録", F(GOTH_B, 26), INK, anchor="ls", alpha=a)
                for i, (dt, s) in enumerate(DEC9):
                    ai = cl((t - a0 - 0.5 - 0.12 * i) / 0.25) * a
                    y = y0 + 108 + 56 * i
                    text(d, (x0 + 26, y), dt, F(GOTH_B, 26), CYAN, anchor="ls", alpha=ai)
                    text(d, (x0 + 120, y), fit_text(d, s, F(GOTH_R, 26), 490), F(GOTH_R, 26), INK, anchor="ls", alpha=ai)
                text(d, (x0 + 26, y0 + 500), "夜に書き足し、朝に読んでから始める", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=cl((t - a0 - 1.6) / 0.3) * a)
            y0 = 40
            for i, (lab, lines, col) in enumerate(TOOLS):
                st = c0 + 0.1 + 0.45 * i
                k = back((t - st) / 0.45); a = cl((t - st) / 0.25) * cols
                if a > 0:
                    x0 = 590 + lerp(60, 0, k)
                    card(d, x0, y0, x0 + 640, y0 + 144, a, outline=col, r=16)
                    tag(d, (x0 + 24, y0 + 48), lab, 28, fg=WHITE, bg_=col, alpha=a)
                    for j, ln in enumerate(lines):
                        text(d, (x0 + 26, y0 + 92 + 36 * j), fit_text(d, ln, F(GOTH_R, 26), 590), F(GOTH_R, 26), INK, anchor="ls", alpha=a)
                y0 += 144 + 16

        # ---- 4 文目: 6 つが動画の場面を同時に作る ／ 前提を知らない 1 つが操作の流れを点検 → 穴 → 直した
        # （点検係が見たのは操作の流れ。6 つの出来上がりを見たのではないので、6 つの箱から矢印は引かない。README と同じ書き方）
        g = cl((t - e0 + 0.1) / 0.3)
        if g > 0:
            tag(d, (60, 74), "11/08", 26, fg=WHITE, bg_=INK, alpha=g)
            wt = d.textlength("11/08", font=F(GOTH_B, 26)) / G["SS"] / G["K"] + 18   # 札の幅（tag と同じ計り方）
            text(d, (60 + wt + 16, 70), "サブエージェント 6 つが、動画の場面を同時に作る", F(GOTH_B, 28), GREEN, anchor="ls", alpha=g)
            bw, gap, x = 180, 16, 60
            for i, s in enumerate(SIX):
                k = back((t - e0 - 0.05 * i) / 0.4); a = cl((t - e0 - 0.05 * i) / 0.2)
                if a <= 0: continue
                bx = x + i * (bw + gap); by = lerp(112, 100, k)
                card(d, bx, by, bx + bw, by + 72, a, outline=GREEN, r=12)
                text(d, (bx + bw / 2, by + 47), fit_text(d, s, F(GOTH_B, 26), bw - 16), F(GOTH_B, 26), INK, anchor="ms", alpha=a)
            t1 = e0 + 0.7
            k = back((t - t1) / 0.45); a = cl((t - t1) / 0.25)
            if a > 0:
                y = lerp(232, 222, k)
                card(d, 300, y, 980, y + 90, a, outline=BLUE, r=14)
                text(d, (640, y + 40), "前提を知らない 1 つが、操作の流れを点検", F(GOTH_B, 30), INK, anchor="ms", alpha=a)
                text(d, (640, y + 74), "作業の文脈を持たず、初めて見る人の目で", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a)
            t2 = e0 + 1.4
            arrow_down(d, 640, 326, 374, cl((t - t2) / 0.25))
            k = back((t - t2 - 0.15) / 0.45); a = cl((t - t2 - 0.15) / 0.25)
            if a > 0:
                y = lerp(392, 382, k)
                card(d, 120, y, 1160, y + 92, a, outline=RED, r=14, op=248)
                tag(d, (144, y + 40), "見つかった穴", 26, fg=WHITE, bg_=RED, alpha=a)
                text(d, (144, y + 80), "一括の確認済が、質問に出る開閉器まで確認済にしていた", F(GOTH_B, 28), INK, anchor="ls", alpha=a)
            t3 = e0 + 2.3
            arrow_down(d, 640, 482, 518, cl((t - t3) / 0.25), col=GREEN)
            k = back((t - t3 - 0.15) / 0.45); a = cl((t - t3 - 0.15) / 0.25)
            if a > 0:
                y = lerp(536, 526, k)
                card(d, 120, y, 1160, y + 92, a, outline=GREEN, r=14, op=248)
                tag(d, (144, y + 40), "直した", 26, fg=WHITE, bg_=GREEN, alpha=a)
                text(d, (144, y + 80), "質問に出る開閉器は、人が確かめるまで未確認のまま", F(GOTH_B, 28), INK, anchor="ls", alpha=a)

        caption(d, "C9", t, False)
        return flatten(f, ov)

    return scene
