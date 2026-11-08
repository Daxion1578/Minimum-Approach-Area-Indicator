"""C9 作り方（v9）。判定は計算・承認は人 → Claude Code で作った → 経験が浅い → 覚えたコマンド 0 と「朝」「終わり」
→ 係とフック → 判断の記録とテストの件数。語り（self.txt の 9 段落目）の 6 文に合わせて順に出す。

compose9.py が make(G) を呼ぶ。G は compose9 の globals。
"""
from __future__ import annotations

TESTS = 104   # 2026-11-08 にリポジトリ直下で MAAI_OFFLINE=1 python -m pytest -q（104 passed）

# docs/decisions.md の日付つきの行から短く（実在の名前・設備名は含まない）
DEC9 = [("11/02", "判定は計算、Claude は意味づけと提案"), ("11/03", "離隔表は「要確認」の印つきで置く"),
        ("11/04", "テストは常にオフラインで回す"), ("11/05", "離隔の既定値を公開資料と照合"),
        ("11/06", "変圧器の取り替えは専用ベイまで止める"), ("11/07", "Claude に送る文のマスクを広げた"),
        ("11/08", "操作を 4 段に絞った")]


def make(G):
    ImageDraw = G["ImageDraw"]
    F, GOTH_B, GOTH_R, MONO = G["F"], G["GOTH_B"], G["GOTH_R"], G["MONO"]
    text, card, tag, bg, cue, caption = G["text"], G["card"], G["tag"], G["bg"], G["cue"], G["caption"]
    new_ov, flatten, fit_text = G["new_ov"], G["flatten"], G["fit_text"]
    cl, lerp, ease, back, smooth = G["cl"], G["lerp"], G["ease"], G["back"], G["smooth"]
    INK, SUBINK, WHITE, BLUE, GREEN, CYAN = G["INK"], G["SUBINK"], G["WHITE"], G["BLUE"], G["GREEN"], G["CYAN"]
    AMBER = G.get("AMBER", (226, 150, 20))
    n = len(G["PARS"]["C9"]["cues"])

    def cs(i):   # i 番目の文の始まり（文が足りないときは最後の文に寄せる）
        return cue("C9", min(i, n - 1))[0]

    # 右の列: 手順（開発は〜）と、係・フック（点検と残りの整理は〜）
    STEPS = [("「朝」と話す", ["外の目の批評 → 残りの整理 → 今日の一つ"], CYAN, 1),
             ("「終わり」と話す", ["テスト → 公開前の点検 → 判断を記録 → 報告"], BLUE, 1),
             ("係を分けた", ["点検係 safety-reviewer は Sonnet", "タスク係 task-keeper は Haiku"], GREEN, 4),
             ("フック", ["commit・push の前に、公開安全チェック", "engine を直したら、テスト"], AMBER, 4)]

    def scene(t, D):
        f = bg(); ov = new_ov(); d = ImageDraw.Draw(ov)
        b0, c0, e0, g0 = cs(1), cs(2), cs(3), cs(4)
        # 台本に「この動画の場面も、係に手分けして作らせた。」が 5 文目の後に入ると文は 7 つ。そのときは 6 文目で札を出し、記録は 7 文目から
        v0, h0 = (cs(5), cs(6)) if n >= 7 else (None, cs(5))
        # 0 判定は計算、承認は人（v8 と同じ 3 つの箱）
        a0 = 1 - cl((t - b0 + 0.25) / 0.35)
        if a0 > 0:
            for i, (lab, who, col) in enumerate((("読む", "Claude", BLUE), ("決める", "計算", INK), ("承認", "人", GREEN))):
                k = back((t - 0.05 - 0.3 * i) / 0.45)
                if k <= 0: continue
                x = 170 + i * 330; y = lerp(240, 210, k)
                card(d, x, y, x + 280, y + 190, a0 * cl(k), outline=col, r=20)
                tag(d, (x + 24, y + 52), lab, 26, fg=WHITE, bg_=col, alpha=a0 * cl(k))
                text(d, (x + 140, y + 142), who, F(GOTH_B, 52), col, anchor="ms", alpha=a0 * cl(k))
                if i < 2: text(d, (x + 305, y + 108), "→", F(GOTH_B, 40), SUBINK, anchor="ms", alpha=a0 * cl(k))
            a = cl((t - 1.3) / 0.3) * a0
            text(d, (640, 500), "Claude の案も、計算で確かめてから出す", F(GOTH_B, 28), SUBINK, anchor="ms", alpha=a)
        b = cl((t - b0) / 0.35)
        if b <= 0:
            caption(d, "C9", t, False); return flatten(f, ov)
        # 1 左: Claude Code で作った
        text(d, (60, 96), "Claude Code", F(GOTH_B, 46), INK, anchor="ls", alpha=b)
        text(d, (62, 136), "で作った（11/02〜11/08）", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=b)
        # 2 作った人（経験が浅い）
        a1 = cl((t - c0) / 0.3)
        if a1 > 0:
            tag(d, (60, 196), "作った人", 24, fg=WHITE, bg_=SUBINK, alpha=a1)
            text(d, (182, 192), "変電所の工事担当", F(GOTH_B, 26), INK, anchor="ls", alpha=a1)
            text(d, (62, 230), "ソフトの開発は、経験が浅い", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a1)
        # 3 覚えたコマンド 0
        a2 = cl((t - e0) / 0.3)
        if a2 > 0:
            text(d, (60, 296), "覚えたコマンド", F(GOTH_B, 30), INK, anchor="ls", alpha=a2)
            text(d, (52, 468), "0", F(GOTH_B, int(round(170 * lerp(1.2, 1.0, ease((t - e0) / 0.4))))), CYAN, anchor="ls", alpha=a2)
            text(d, (196, 406), "言葉で", F(GOTH_B, 30), INK, anchor="ls", alpha=a2)
            text(d, (196, 448), "頼むだけ", F(GOTH_B, 30), INK, anchor="ls", alpha=a2)
        # 5'（文が 7 つのときだけ）動画の場面づくりも係に手分け
        if v0 is not None:
            av = cl((t - v0) / 0.3) * (1 - cl((t - h0 + 0.25) / 0.3))
            if av > 0:
                kv = back((t - v0) / 0.45)
                card(d, 60, 492, 560, 606, av, outline=GREEN, r=16, op=246)
                tag(d, (84, 536), "動画の場面づくり", 24, fg=WHITE, bg_=GREEN, alpha=av)
                text(d, (84 + (1 - cl(kv)) * 14, 586), "6 つの係が同時に（11/08）", F(GOTH_B, 28), INK, anchor="ls", alpha=av)
        # 5 テストの件数
        a3 = cl((t - h0 - 0.4) / 0.3)
        if a3 > 0:
            text(d, (60, 540), f"テスト {TESTS} 件", F(GOTH_B, 30), INK, anchor="ls", alpha=a3)
            text(d, (60, 578), "push のたびに通しの確認", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=a3)
        # 右: 手順（1〜）→ 係・フック（4〜）→ 判断の記録（5〜）
        out = smooth((t - h0 + 0.35) / 0.4)
        y0 = 40
        for i, (lab, lines, col, at) in enumerate(STEPS):
            h = 104 if len(lines) == 1 else 140
            st = b0 + 0.25 + 0.3 * i if at == 1 else g0 + 0.3 * (i - 2)
            k = back((t - st) / 0.45); a = cl(k) * (1 - out)
            if a > 0:
                x0 = 590 + lerp(60, 0, k) + 80 * out
                card(d, x0, y0, x0 + 640, y0 + h, a, outline=col, r=16)
                text(d, (x0 + 26, y0 + 44), lab, F(GOTH_B, 30), col, anchor="ls", alpha=a)
                for j, ln in enumerate(lines):
                    text(d, (x0 + 26, y0 + 86 + 36 * j), fit_text(d, ln, F(GOTH_R, 26), 590), F(GOTH_R, 26), INK, anchor="ls", alpha=a)
            y0 += h + 16
        k = back((t - h0 + 0.1) / 0.5); a = cl((t - h0 + 0.1) / 0.25)
        if a > 0:
            x0 = 590 + lerp(80, 0, k); y0 = 40
            card(d, x0, y0, x0 + 640, y0 + 560, a, outline=(200, 212, 224), r=16, op=250)
            text(d, (x0 + 26, y0 + 50), "docs/decisions.md", F(MONO, 26), BLUE, anchor="ls", alpha=a)
            text(d, (x0 + 290, y0 + 50), "判断の記録", F(GOTH_B, 26), INK, anchor="ls", alpha=a)
            for i, (dt, s) in enumerate(DEC9):
                ai = cl((t - h0 - 0.1 - 0.12 * i) / 0.25) * a
                y = y0 + 112 + 58 * i
                text(d, (x0 + 26, y), dt, F(GOTH_B, 26), CYAN, anchor="ls", alpha=ai)
                text(d, (x0 + 120, y), fit_text(d, s, F(GOTH_R, 26), 490), F(GOTH_R, 26), INK, anchor="ls", alpha=ai)
            text(d, (x0 + 26, y0 + 538), "夜に書き足し、朝に読んでから始める", F(GOTH_R, 24), SUBINK, anchor="ls", alpha=cl((t - h0 - 1.2) / 0.3) * a)
        caption(d, "C9", t, False)
        return flatten(f, ov)

    return scene
