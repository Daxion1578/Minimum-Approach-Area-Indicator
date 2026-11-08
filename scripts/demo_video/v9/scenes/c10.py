"""C10 締め（v9）。資材置場の上のクレーン（r9/safe.jpg、無ければ v8 の r7/z_safe.jpg）→「見えない間合いを、見えるように。」
→ 名前・注記・GitHub。読み上げの表記は、VOICEVOX の声が残っているとき（timing.json の credit か src が voicevox）だけ出す。

compose9.py が make(G) を呼ぶ。G は compose9 の globals。
"""
from __future__ import annotations


def make(G):
    ImageDraw, Image = G["ImageDraw"], G["Image"]
    F, GOTH_B, GOTH_R = G["F"], G["GOTH_B"], G["GOTH_R"]
    text, seg, bg, kw, caption, cam, blend = G["text"], G["seg"], G["bg"], G["kw"], G["caption"], G["cam"], G["blend"]
    new_ov, flatten, narr_end = G["new_ov"], G["flatten"], G["narr_end"]
    cl, ease, back, smooth = G["cl"], G["ease"], G["back"], G["smooth"]
    INK, SUBINK, CYAN = G["INK"], G["SUBINK"], G["CYAN"]
    T, HERE = G["T"], G["HERE"]

    r9 = HERE / "assets" / "r9"
    src = Image.open(r9 / "safe.jpg").convert("RGB") if (r9 / "points.json").exists() and (r9 / "safe.jpg").exists() else G["Z8"]
    vv = [p["p"] for p in T["paragraphs"] if p.get("src") == "voicevox"]
    credit = T.get("credit") or ("VOICEVOX:冥鳴ひまり（仮の読み上げ）" if vv else "")

    def scene(t, D):
        ke = narr_end("C10") - 0.2
        kt = kw("C10", "見えない", ke - 1.5)
        z = 1 + 0.08 * (t / D)
        f3, _ = cam(src, z, (src.width / 2 - 80 * (z - 1) / 0.08 * src.width / 1920, src.height / 2))
        kp = smooth((t - kt) / 0.9)
        f = blend(f3, bg(), kp)
        ov = new_ov(); d = ImageDraw.Draw(ov)
        if kp > 0:
            text(d, (640, 300), "見えない間合いを、見えるように。", F(GOTH_B, 52), INK, anchor="ms", alpha=cl((t - kt) / 0.3))
            seg(d, (330, 330), (330 + 620 * ease((t - kt - 0.3) / 0.6), 330), 1, CYAN, 6)
            text(d, (640, 392), "MAAI（間合い）", F(GOTH_B, 34), CYAN, anchor="ms", alpha=cl((t - kt - 1.0) / 0.5))
            a2 = cl((t - kt - 1.6) / 0.5)
            text(d, (640, 560), "データはすべて合成です。実在の事業者・設備・図面は含みません。", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a2)
            if credit:
                text(d, (640, 596), f"読み上げ {credit}", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a2)
            text(d, (640, 632 if credit else 600), "github.com/Daxion1578/Minimum-Approach-Area-Indicator", F(GOTH_R, 24), SUBINK, anchor="ms", alpha=a2)
        if kp < 0.05:
            caption(d, "C10", t, True)
        return flatten(f, ov)

    return scene
