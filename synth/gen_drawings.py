#!/usr/bin/env python3
"""
合成変電所 SITE-01 の図面 3 枚（ベクター PDF）を、truth の topology / layout から生成する。

  python -m synth.gen_drawings            # data/sites/SITE-01/drawings/ に 3 枚

  SITE-01_sld.pdf       単線結線図   A3 横、縮尺なし
  SITE-01_plan.pdf      一般平面図   A3 横、1/1000（敷地・周辺・建物・道路）
  SITE-01_layout.pdf    機械器具装置図 A1 横、平面 1/400 ＋ 断面 1/400（変圧器を母線に垂直に切る）

描き方は、変電所図面の一般的な流儀に合わせる（出典は特定の事業者の規程ではなく、合成のための約束）:
  - 主回路は右を高圧、左へ低圧。機器の並びは現場配置に合わせる
  - 線の太さは電圧階級で変える（220kV 太、66kV 中、補助 細）
  - 開閉器番号は記号の右、仕様は記号の下。母線は「1号・2号」と導体種別。送電線は線路名と（給電名称）
  - 図記号は JIS C 0617 を既定（--symbols circle で ○／⊗ の流儀にも出せる）
  - 文字 2〜5mm、図面名 7mm。輪郭は左 35mm・他 10mm。表題欄は右下
文字はすべて PDF のテキストとして入る（画素ではない）。寸法・名称はすべて仮定値。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib

from reportlab.lib.pagesizes import A1, A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from synth.gen_site import P, PHASE_IDX, PHASES, SITE_ID

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRUTH = ROOT / "data" / "sites" / SITE_ID / "truth"
OUT = ROOT / "data" / "sites" / SITE_ID / "drawings"
MM = 72 / 25.4
DATE_TEXT = "令和8年11月4日"
OFFICE = "合成送配電センター　合成地区　合成変電所"

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "C:/Windows/Fonts/msgothic.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
]

# 線幅（pt）: 電圧階級ごと。補助回路・寸法線は細線
LW = {220: 1.3, 66: 0.9, "aux": 0.35, "dim": 0.25, "thin": 0.3, "frame": 0.8}

# ---- 仮定値: 敷地・周辺（一般平面図・装置図で使う）----
SITE = {
    "fence": (-22.0, -120.0, 113.0, 14.0),   # x_min, y_min, x_max, y_max（外柵）
    "building": (60.0, -72.0, 74.0, -58.0),  # 本館 14m×14m
    "roads": [(-22.0, -52.0, 113.0, -46.0),  # 構内道路 幅 6m（220kV 配開と変圧器の間）
              (-22.0, -70.0, 113.0, -64.0),  # 構内道路 幅 6m（変圧器と 66kV 配開の間）
              (78.0, -120.0, 84.0, -46.0)],  # 南北道路（東側）
    "gate": (113.0, -52.0, 113.0, -46.0),
    "tank": (90.0, -40.0),                   # 碍洗用水槽
    "oil_sep": (30.0, -50.0),                # 油水分離槽
    "outside_road": (-42.0, -140.0, 133.0, -126.0),  # 社有地外の道路（南）
}


def setup_font() -> str:
    for p in FONT_CANDIDATES:
        if pathlib.Path(p).exists():
            try:
                pdfmetrics.registerFont(TTFont("JP", p))
                return "JP"
            except Exception:
                continue
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    return "HeiseiKakuGo-W5"


class Sheet:
    """図面 1 枚。紙の座標は mm（左下原点）。図枠・表題欄を持つ。"""

    def __init__(self, path, pagesize, font, name, number, scale_text):
        self.c = canvas.Canvas(str(path), pagesize=landscape(pagesize))
        self.w, self.h = (v / MM for v in landscape(pagesize))
        self.font = font
        self.c.setLineWidth(LW["frame"])
        self.c.rect(35 * MM, 10 * MM, (self.w - 45) * MM, (self.h - 20) * MM)   # 輪郭: 左 35、他 10
        self.title_block(name, number, scale_text)

    # ---- 紙の座標（mm）で描く基本要素 ----
    def line(self, x1, y1, x2, y2, w=LW["thin"], dash=None, gray=0.0):
        c = self.c
        c.setLineWidth(w); c.setStrokeGray(gray); c.setDash(dash or [])
        c.line(x1 * MM, y1 * MM, x2 * MM, y2 * MM); c.setDash([])

    def poly(self, pts, w=LW["thin"], dash=None, gray=0.0, close=False):
        pts = list(pts) + ([pts[0]] if close else [])
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            self.line(x1, y1, x2, y2, w, dash, gray)

    def rect(self, x, y, w_, h_, w=LW["thin"], fill_gray=None, dash=None):
        c = self.c
        c.setLineWidth(w); c.setStrokeGray(0); c.setDash(dash or [])
        if fill_gray is not None:
            c.setFillGray(fill_gray)
        c.rect(x * MM, y * MM, w_ * MM, h_ * MM, fill=fill_gray is not None); c.setDash([]); c.setFillGray(0)

    def circle(self, x, y, r, w=LW["thin"], fill=False):
        self.c.setLineWidth(w); self.c.setStrokeGray(0); self.c.setFillGray(0)
        self.c.circle(x * MM, y * MM, r * MM, fill=fill)

    def text(self, x, y, s, size_mm=2.5, angle=0, anchor="sw", gray=0.0):
        size = size_mm * MM
        c = self.c
        c.saveState(); c.setFillGray(gray); c.setFont(self.font, size)
        c.translate(x * MM, y * MM); c.rotate(angle)
        tw = pdfmetrics.stringWidth(s, self.font, size)
        dx = {"sw": 0.0, "s": -tw / 2, "se": -tw, "c": -tw / 2, "w": 0.0, "e": -tw}[anchor]
        dy = -size / 2.8 if anchor in ("c", "w", "e") else 0.0
        c.drawString(dx, dy, s); c.restoreState()

    def dim(self, x1, y1, x2, y2, label, off=4.0, size_mm=2.5):
        """寸法線。水平または垂直。off は寸法線のオフセット（mm、符号つき）。"""
        if abs(x1 - x2) < 1e-6:   # 垂直
            xo = x1 + off
            self.line(x1, y1, xo + math.copysign(1.0, off), y1, LW["dim"])
            self.line(x1, y2, xo + math.copysign(1.0, off), y2, LW["dim"])
            self.line(xo, y1, xo, y2, LW["dim"])
            for y in (y1, y2):
                self.line(xo - 0.7, y - 0.7, xo + 0.7, y + 0.7, LW["dim"])
            self.text(xo + (0.8 if off > 0 else -0.8), (y1 + y2) / 2, label, size_mm, angle=90, anchor="s" if off > 0 else "s")
        else:
            yo = y1 + off
            self.line(x1, y1, x1, yo + math.copysign(1.0, off), LW["dim"])
            self.line(x2, y2, x2, yo + math.copysign(1.0, off), LW["dim"])
            self.line(x1, yo, x2, yo, LW["dim"])
            for x in (x1, x2):
                self.line(x - 0.7, yo - 0.7, x + 0.7, yo + 0.7, LW["dim"])
            self.text((x1 + x2) / 2, yo + (0.8 if off > 0 else -3.0), label, size_mm, anchor="s")

    def title_block(self, name, number, scale_text):
        W, H = 140.0, 28.0
        x, y = self.w - 10 - W, 10.0
        self.rect(x, y, W, H, LW["frame"])
        self.line(x, y + 16, x + W, y + 16, LW["thin"])
        self.line(x + 80, y, x + 80, y + 16, LW["thin"])
        self.text(x + 4, y + 19.5, name, 7.0)
        self.text(x + 95, y + 20, OFFICE, 2.5)
        self.text(x + 4, y + 11, "作成年月日　" + DATE_TEXT, 2.5)
        self.text(x + 4, y + 6.5, "縮尺　" + scale_text, 2.5)
        self.text(x + 4, y + 2, "合成変電所（架空）。寸法・名称・番号はすべて仮定値", 2.2)
        self.text(x + 84, y + 11, "図番", 2.5); self.text(x + 95, y + 11, number, 3.5)
        self.text(x + 84, y + 4, "生成 synth/gen_drawings.py", 2.2)

    def north(self, x, y, r=6.0):
        self.circle(x, y, r); self.line(x, y - r, x, y + r, LW["thin"])
        self.poly([(x, y + r), (x - 1.5, y + r - 5), (x + 1.5, y + r - 5)], LW["thin"], close=True)
        self.text(x, y + r + 1.5, "N", 3.0, anchor="s")

    def save(self):
        self.c.showPage(); self.c.save()


# --------------------------------------------------------------------------
# 単線結線図
# --------------------------------------------------------------------------
class SLD:
    def __init__(self, sh: Sheet, topo: dict, symbols: str):
        self.sh, self.symbols = sh, symbols
        self.nodes = {n["id"]: n for n in topo["nodes"]}

    def num(self, nid):
        return self.nodes[nid].get("number", "")

    # ---- 図記号（紙 mm）。縦の母線枝の上に描く。gap は記号の半長 ----
    def cb(self, x, y, kv, nid):
        w = LW[kv]
        if self.symbols == "circle":
            self.sh.circle(x, y, 2.0, w)
        else:  # JIS C 0617: 接点（斜めの可動片）＋ 固定側に ×
            self.sh.line(x, y - 2.5, x + 1.6, y + 2.0, w)
            self.sh.line(x - 0.9, y + 1.6, x + 0.9, y + 3.4, w); self.sh.line(x - 0.9, y + 3.4, x + 0.9, y + 1.6, w)
        self.sh.text(x + 2.6, y - 0.8, self.num(nid), 2.2)

    def ds(self, x, y, kv, nid, earth=False, panto=False):
        w = LW[kv]
        if self.symbols == "circle":
            self.sh.circle(x, y, 1.8, w); self.sh.line(x - 1.3, y - 1.3, x + 1.3, y + 1.3, w); self.sh.line(x - 1.3, y + 1.3, x + 1.3, y - 1.3, w)
        else:  # JIS: 斜めの可動片＋固定側の横棒。パンタ型は二重線
            self.sh.line(x, y - 2.5, x + 1.6, y + 2.0, w)
            self.sh.line(x - 1.2, y + 2.5, x + 1.2, y + 2.5, w)
            if panto:
                self.sh.line(x - 1.2, y + 3.2, x + 1.2, y + 3.2, w)
        if earth:
            self.ground(x + 4.0, y, kv)
            self.sh.line(x, y - 2.5, x + 4.0, y - 2.5, LW["aux"])
        self.sh.text(x + 2.6, y - 0.8, self.num(nid), 2.2)

    def ground(self, x, y, kv):
        self.sh.line(x, y - 2.5, x, y - 5.0, LW["aux"])
        for i, hw in enumerate((2.0, 1.3, 0.6)):
            self.sh.line(x - hw, y - 5.0 - i * 0.9, x + hw, y - 5.0 - i * 0.9, LW["aux"])

    def es_mark(self, x, y, kv, nid):
        """接地開閉器（区間の点検用）。枝から横に出して接地。"""
        self.sh.line(x, y, x - 3.0, y, LW["aux"])
        self.sh.line(x - 3.0, y + 1.2, x - 4.2, y - 1.0, LW["aux"])
        self.ground(x - 4.2, y + 1.5, kv)
        self.sh.text(x - 4.5, y + 1.0, self.num(nid), 1.8, anchor="se")

    def transformer(self, x, y, nid, label):
        self.sh.circle(x, y + 2.2, 3.0, LW[220]); self.sh.circle(x, y - 2.2, 3.0, LW[66])
        self.sh.text(x + 4.0, y + 1.0, self.num(nid), 2.5)
        self.sh.text(x + 4.0, y - 2.5, label, 2.0)

    def dot(self, x, y):
        self.sh.c.setFillGray(0); self.sh.c.circle(x * MM, y * MM, 0.6 * MM, fill=1, stroke=0)

    def arrow(self, x, y, up, kv):
        d = 1.0 if up else -1.0
        self.sh.line(x, y, x - 1.2, y - 2.0 * d, LW[kv]); self.sh.line(x, y, x + 1.2, y - 2.0 * d, LW[kv])

    # ---- 1・1/2 母線の 1 構内 ----
    def yard(self, vl, x_left, pitch, y_bus1, y_bus2, line_dir, tr_dir):
        cfg = P[vl]; kv = cfg["kv"]; w = LW[kv]; sh = self.sh
        n = len(cfg["bays"])
        x_right = x_left + pitch * (n - 1) + 12
        for yb, lab in ((y_bus1, "1号母線"), (y_bus2, "2号母線")):
            sh.line(x_left - 24, yb, x_right, yb, w * 1.6)
            sh.text(x_left - 24, yb + 1.2, f"{kv}kV {lab}", 2.5)
            sh.text(x_left - 24, yb - 3.0, "PAℓ 150φ×6" if kv == 220 else "HAℓ 410×1", 2.0)
        ys = {}
        step = (y_bus1 - y_bus2) / 10.0
        keys = ["LSA", "CB1", "LS1B", "T1", "LS2A", "CB2", "LS2B", "T2", "LS3A", "CB3", "LSB"]
        for i, k in enumerate(keys):
            ys[k] = y_bus1 - step * (i + 0.5) + (step * 0.5 if k in ("T1", "T2") else 0)
        ys = {k: y_bus1 - step * (i + 0.6) for i, k in enumerate(keys)}
        panto = (kv == 220)
        tr_xy = {}
        for i, (bay, c1, c2) in enumerate(cfg["bays"]):
            x = x_left + i * pitch
            pre = f"{vl}-{bay}"
            new_bay = (c1 is None and c2 is None)
            sh.text(x, y_bus1 + 5.0, f"{kv}kV {bay}", 2.5, anchor="s", gray=0.0)
            sh.line(x, y_bus1, x, y_bus2, w, dash=[2, 1.5] if new_bay else None)
            if not new_bay:
                self.dot(x, y_bus1); self.dot(x, y_bus2)
            for k in ("LSA", "LS1B", "LS2A", "LS2B", "LS3A", "LSB"):
                self.ds(x, ys[k], kv, f"{pre}-{k}", panto=panto)
            for k in ("CB1", "CB2", "CB3"):
                self.cb(x, ys[k], kv, f"{pre}-{k}")
            if new_bay:
                sh.text(x + 3.0, ys["T1"], "（新設予定）", 2.2, anchor="w"); sh.text(x + 3.0, ys["T2"], "（新設予定）", 2.2, anchor="w")
                continue
            # 点検用の接地開閉器（区間ごと）
            for k, yk in (("N1", (ys["LSA"] + ys["CB1"]) / 2), ("N2", (ys["CB1"] + ys["LS1B"]) / 2), ("N3", (ys["LS2A"] + ys["CB2"]) / 2),
                          ("N4", (ys["CB2"] + ys["LS2B"]) / 2), ("N5", (ys["LS3A"] + ys["CB3"]) / 2), ("N6", (ys["CB3"] + ys["LSB"]) / 2)):
                self.es_mark(x, yk, kv, f"{pre}-{k}-ES")
            # 回路（T1 北側 / T2 南側）: 横に引き出して、線路は矢印、変圧器は記号へ
            for k, c, up in (("T1", c1, line_dir), ("T2", c2, line_dir)):
                yk = ys[k]
                kind, cid, cname = c
                # 線路が相手の引出線を横切る側（T1 が下へ／T2 が上へ）は内側に出す。交差は接続点なしの「交わり」
                crossing = kind == "line" and ((k == "T1" and not up) or (k == "T2" and up))
                xo = x + pitch / 2.0 - (9.0 if crossing else 0.0)
                sh.line(x, yk, xo, yk, w); self.dot(x, yk)
                if kind == "line":
                    ln = f"{vl}-LINE-{cid}"
                    self.ds(xo, yk, kv, f"{ln}-LS", earth=True, panto=panto)
                    yend = (y_bus1 + 20.0) if up else (y_bus2 - 18.0)
                    sh.line(xo, yk, xo, yend, w); self.arrow(xo, yend, up, kv)
                    anc = "se" if crossing else "sw"
                    tx = xo - 1.5 if crossing else xo + 1.5
                    sh.text(tx, yend + (-3.5 if up else 1.0), f"{cname}（{cname[0]}{cname[-2:]}）", 2.5, anchor=anc)
                    sh.text(tx, yend + (-6.5 if up else -2.0), "ACSR 410×1" if kv == 220 else "ACSR 160×1", 2.0, anchor=anc)
                else:
                    tid = f"{vl}-TR-{cid}-LS"
                    self.ds(xo, yk, kv, tid, earth=True, panto=panto)
                    yend = (y_bus2 - 18.0) if tr_dir == "down" else (y_bus1 + 8.0)
                    sh.line(xo, yk, xo, yend, w)
                    tr_xy[cid] = (xo, yend)
        return tr_xy

    def draw(self):
        sh = self.sh
        sh.text(40, sh.h - 16, "記号は JIS C 0617 による。開閉器番号は記号の右。母線・線路は導体種別を併記。", 2.2)
        # 220kV（右）: 母線 y=235 / 160、ダイヤ 4 本。線路は上へ、変圧器は下へ
        tr220 = self.yard("220", 232, 44, 258, 160, line_dir=True, tr_dir="down")
        # 66kV（左）: 変圧器二次は上へ（T1）、線路は下へ
        tr66 = self.yard("66", 62, 40, 106, 38, line_dir=False, tr_dir="up")
        # 変圧器（1BK・2BK）: 220 側の引出し末端と 66 側の末端を結ぶ
        for n in sorted(tr220):
            (x1, y1), (x2, y2) = tr220[n], tr66[n]
            ty = 130.0
            tx = x1
            sh.line(x1, y1, tx, ty + 5.5, LW[220])
            self.transformer(tx, ty, f"TR-{n}", "220/66kV 三相")
            ym = 121.0 - (n - 1) * 3.0
            sh.line(tx, ty - 5.5, tx, ym, LW[66]); sh.line(tx, ym, x2, ym, LW[66]); sh.line(x2, ym, x2, y2, LW[66])
        # 主要機器の概要欄
        x0, y0 = 42, 150
        sh.rect(x0, y0, 150, 26, LW["thin"])
        sh.text(x0 + 2, y0 + 21.5, "主要機器の概要（仮定値）", 2.8)
        sh.text(x0 + 2, y0 + 15.5, "1BK　三相変圧器　220/66kV　製年 —　製造者 —", 2.3)
        sh.text(x0 + 2, y0 + 10.5, "2BK　三相変圧器　220/66kV　製年 —　製造者 —", 2.3)
        sh.text(x0 + 2, y0 + 5.5, "母線形態　220kV・66kV とも 1・1/2 母線　　接地線　A種　軟銅より線", 2.3)
        sh.text(x0 + 2, y0 + 1.0, "監視制御箇所　合成制御所　　保守担当箇所　合成技術センター", 2.3)
        sh.text(40, sh.h - 22, "単線結線図（主回路）", 4.0)


# --------------------------------------------------------------------------
# 一般平面図（1/1000）
# --------------------------------------------------------------------------
class Plan:
    def __init__(self, sh: Sheet, layout: dict, scale: float, ox: float, oy: float):
        self.sh, self.layout, self.s = sh, layout, scale
        self.ox, self.oy = ox, oy
        self.items = {i["id"]: i for i in layout["items"]}

    def X(self, x): return self.ox + x * self.s
    def Y(self, y): return self.oy + y * self.s

    def rect_m(self, x1, y1, x2, y2, w=LW["thin"], dash=None, fill_gray=None):
        self.sh.rect(self.X(min(x1, x2)), self.Y(min(y1, y2)), abs(x2 - x1) * self.s, abs(y2 - y1) * self.s, w, fill_gray, dash)

    def line_m(self, x1, y1, x2, y2, w=LW["thin"], dash=None, gray=0.0):
        self.sh.line(self.X(x1), self.Y(y1), self.X(x2), self.Y(y2), w, dash, gray)

    def text_m(self, x, y, s, size=2.5, anchor="sw", angle=0):
        self.sh.text(self.X(x), self.Y(y), s, size, angle, anchor)

    def fence(self):
        x1, y1, x2, y2 = SITE["fence"]
        self.rect_m(x1, y1, x2, y2, LW["aux"])
        self.rect_m(x1 - 1.5, y1 - 1.5, x2 + 1.5, y2 + 1.5, LW["aux"], dash=[1.2, 0.8])   # 二重外柵
        self.text_m(x1, y2 + 3, "敷地境界（外柵）", 2.2)

    def roads_buildings(self, detail=True):
        for r in SITE["roads"]:
            self.rect_m(*r, w=LW["thin"], fill_gray=0.93)
        bx1, by1, bx2, by2 = SITE["building"]
        self.rect_m(bx1, by1, bx2, by2, LW["frame"])
        self.text_m((bx1 + bx2) / 2, (by1 + by2) / 2 + 1, "本館", 2.5, anchor="c"); self.text_m((bx1 + bx2) / 2, (by1 + by2) / 2 - 2.5, "RC 2階", 2.0, anchor="c")
        gx, gy1, _, gy2 = SITE["gate"]
        self.line_m(gx, gy1, gx + 4, gy1 - 3, LW["thin"]); self.line_m(gx, gy2, gx + 4, gy2 + 3, LW["thin"]); self.text_m(gx + 5, (gy1 + gy2) / 2, "門扉（入口）", 2.2, anchor="w")
        tx, ty = SITE["tank"]; self.sh.circle(self.X(tx), self.Y(ty), 3.0 * self.s); self.text_m(tx + 4, ty, "碍洗用水槽", 2.0, anchor="w")
        ox_, oy_ = SITE["oil_sep"]; self.rect_m(ox_ - 2, oy_ - 1.5, ox_ + 2, oy_ + 1.5); self.text_m(ox_ + 3, oy_, "油水分離槽", 2.0, anchor="w")

    def equipment_outline(self):
        """一般平面図用: 機器配置の略図（構内ごとの外形と母線・変圧器だけ）。"""
        for vl in ("220", "66"):
            cfg = P[vl]; n = len(cfg["bays"]); sp = cfg["phase_sp"]
            x1 = cfg["x0"] - cfg["bay_pitch"] / 2; x2 = cfg["x0"] + cfg["bay_pitch"] * (n - 0.5)
            yN, yS = cfg["line_y"]
            self.rect_m(x1, yS, x2, yN, LW["thin"], dash=[1.5, 1.0])
            self.text_m(x1 + 1, yN - 4, f"{cfg['kv']}kV 配開設備（1・1/2 母線）", 2.5)
            for b in ("busA", "busB"):
                for ph in PHASES:
                    y = cfg[b]["y"] - PHASE_IDX[ph] * sp
                    self.line_m(x1, y, x2, y, LW["frame"])
            for i, (bay, c1, c2) in enumerate(cfg["bays"]):
                x = cfg["x0"] + i * cfg["bay_pitch"]
                self.line_m(x, cfg["busA"]["y"], x, cfg["busB"]["y"], LW["thin"])
                self.text_m(x, yN + 1, bay, 2.0, anchor="s")
        for n in (1, 2):
            at = self.items[f"TR-{n}"]["at"]
            self.rect_m(at[0] - 3, at[1] - 2.5, at[0] + 3, at[1] + 2.5, LW["frame"])
            self.text_m(at[0], at[1] - 5, f"{n}BK", 2.2, anchor="s")

    def surroundings(self):
        x1, y1, x2, y2 = SITE["fence"]
        rx1, ry1, rx2, ry2 = SITE["outside_road"]
        self.line_m(rx1, ry2, rx2, ry2, LW["thin"]); self.line_m(rx1, ry1, rx2, ry1, LW["thin"])
        self.text_m((rx1 + rx2) / 2, (ry1 + ry2) / 2, "市道（至 合成町）", 2.5, anchor="c")
        self.text_m(rx1, (ry1 + ry2) / 2 - 1, "至 合成駅 ←", 2.2); self.text_m(rx2, (ry1 + ry2) / 2 - 1, "→ 至 合成港", 2.2, anchor="se")
        # 送電線引出ルート: 220kV は北へ（鉄塔）、66kV は南へ
        cfg = P["220"]
        for i, (bay, c1, c2) in enumerate(cfg["bays"]):
            if c1 is None:
                continue
            x = cfg["x0"] + i * cfg["bay_pitch"]
            self.line_m(x, cfg["line_y"][0], x, y2 + 22, LW["thin"], dash=[3, 1.5])
            self.tower(x, y2 + 22); self.text_m(x + 2, y2 + 24, f"{c1[2]}", 2.0)
            if c2 and c2[0] == "line":
                self.line_m(x, cfg["line_y"][1], x + 30, y1 - 8, LW["thin"], dash=[3, 1.5]) if False else None
        cfg = P["66"]
        for i, (bay, c1, c2) in enumerate(cfg["bays"]):
            x = cfg["x0"] + i * cfg["bay_pitch"]
            self.line_m(x, cfg["line_y"][1], x, y1 - 18, LW["thin"], dash=[3, 1.5])
            self.tower(x, y1 - 18, 1.5); self.text_m(x + 1.5, y1 - 22, f"{(c2 or c1)[2]}", 1.8)
        self.text_m(x1 - 18, y1 - 25, "水田", 3.0); self.text_m(x2 + 5, y2 - 30, "畑", 3.0); self.text_m(x1 - 18, y2 - 20, "荒地", 3.0)

    def tower(self, x, y, r=2.5):
        X, Y, r = self.X(x), self.Y(y), r * self.s
        self.sh.rect(X - r, Y - r, 2 * r, 2 * r, LW["thin"]); self.sh.line(X - r, Y - r, X + r, Y + r, LW["thin"]); self.sh.line(X - r, Y + r, X + r, Y - r, LW["thin"])

    def info_table(self, x, y):
        rows = [("縮尺", "1/1,000"), ("敷地面積", "18,090 ㎡（135m × 134m）"), ("建物（本館）", "鉄筋コンクリート造 2階　平面 196 ㎡　延べ 392 ㎡　2026年（合成）"),
                ("用途地域", "工業地域（合成）"), ("供給地域", "合成送配電センター 合成地区"), ("記載範囲", "社有地外 20m 程度まで")]
        self.sh.rect(x, y, 150, 6 * 6.5 + 2, LW["thin"])
        for i, (k, v) in enumerate(rows):
            yy = y + 6 * 6.5 - i * 6.5 - 3.5
            self.sh.text(x + 2, yy, k, 2.5); self.sh.text(x + 32, yy, v, 2.3)
            if i:
                self.sh.line(x, yy + 5.0, x + 150, yy + 5.0, LW["dim"])
        self.sh.line(x + 30, y, x + 30, y + 6 * 6.5 + 2, LW["dim"])


# --------------------------------------------------------------------------
# 機械器具装置図（平面 ＋ 断面）
# --------------------------------------------------------------------------
class LayoutDrawing(Plan):
    def grid_lines(self):
        """通り芯: X は 220kV/66kV のベイ中心、Y は母線・変圧器列。バルーンつき。"""
        x1, y1, x2, y2 = SITE["fence"]
        xs = [("X%d" % (i + 1), P["220"]["x0"] + i * P["220"]["bay_pitch"]) for i in range(4)]
        xs += [("x%d" % (i + 1), P["66"]["x0"] + i * P["66"]["bay_pitch"]) for i in range(4)]
        ys = [("Y1", P["220"]["busA"]["y"]), ("Y2", P["220"]["busB"]["y"]), ("Y3", P["220"]["tr_y"]), ("Y4", P["66"]["busA"]["y"]), ("Y5", P["66"]["busB"]["y"])]
        for lab, x in xs:
            top = lab.startswith("X")
            ya, yb = (P["66"]["line_y"][0] + 2, y2) if top else (y1, P["66"]["line_y"][0] + 2)
            self.line_m(x, ya, x, yb, LW["dim"], dash=[6, 1.2, 1.2, 1.2], gray=0.35)
            yy = self.Y(y2) + (6 if top else -6) * (1 if top else 1)
            if top:
                self.sh.circle(self.X(x), self.Y(y2) + 7, 3.0); self.sh.text(self.X(x), self.Y(y2) + 7, lab, 2.5, anchor="c")
            else:
                self.sh.circle(self.X(x), self.Y(y1) - 7, 3.0); self.sh.text(self.X(x), self.Y(y1) - 7, lab, 2.5, anchor="c")
        for lab, y in ys:
            self.line_m(x1, y, x2, y, LW["dim"], dash=[6, 1.2, 1.2, 1.2], gray=0.35)
            self.sh.circle(self.X(x1) - 7, self.Y(y), 3.0); self.sh.text(self.X(x1) - 7, self.Y(y), lab, 2.5, anchor="c")
        # 寸法: ベイ間隔・母線間
        yd = self.Y(y2) + 14
        for i in range(3):
            xa, xb = xs[i][1], xs[i + 1][1]
            self.sh.dim(self.X(xa), yd, self.X(xb), yd, "16,000", off=0)
        xd = self.X(x1) - 14
        self.sh.dim(xd, self.Y(ys[0][1]), xd, self.Y(ys[1][1]), "36,000", off=0)
        self.sh.dim(xd, self.Y(ys[1][1]), xd, self.Y(ys[2][1]), "22,000", off=0)
        self.sh.dim(xd, self.Y(ys[2][1]), xd, self.Y(ys[3][1]), "22,000", off=0)
        self.sh.dim(xd, self.Y(ys[3][1]), xd, self.Y(ys[4][1]), "24,000", off=0)
        yd2 = self.Y(y1) - 14
        for i in range(4, 7):
            xa, xb = xs[i][1], xs[i + 1][1]
            self.sh.dim(self.X(xa), yd2, self.X(xb), yd2, "7,000", off=0)

    def equipment_plan(self, topo):
        nodes = {n["id"]: n for n in topo["nodes"]}
        for vl in ("220", "66"):
            cfg = P[vl]; sp = cfg["phase_sp"]; n = len(cfg["bays"])
            x1 = cfg["x0"] - cfg["bay_pitch"] / 2 - 1; x2 = cfg["x0"] + cfg["bay_pitch"] * (n - 0.5) + 1
            # 母線（相ごと太線）と引留鉄構
            for b in ("busA", "busB"):
                for ph in PHASES:
                    y = cfg[b]["y"] - PHASE_IDX[ph] * sp
                    self.line_m(x1, y, x2, y, LW[cfg["kv"]])
                for xg in (x1, x2):
                    self.gantry(xg, cfg[b]["y"], 2 * sp + 2.0, along="y")
                self.text_m(x2 + 2, cfg[b]["y"], f"{cfg['kv']}kV {'1号' if b == 'busA' else '2号'}母線", 2.2, anchor="w")
            # 引留鉄構（線路側）と架空地線
            for yg in cfg["line_y"]:
                self.gantry_line(x1, x2, yg)
        # 機器: 開閉器（3 相の台）、接地開閉器、変圧器
        for it in self.layout["items"]:
            nid = it["id"]; node = nodes.get(nid)
            if node is None or "at" not in it:
                continue
            x, y, _ = it["at"]; kind = node["kind"]; kv = node.get("voltage_kv", 220)
            sp = P["220" if kv == 220 else "66"]["phase_sp"]
            if kind == "breaker":
                for ph in PHASES:
                    px = x + PHASE_IDX[ph] * sp
                    self.rect_m(px - 0.7, y - 1.2, px + 0.7, y + 1.2, LW["thin"])
                self.text_m(x + sp + 1.2, y, node.get("number", ""), 1.6, anchor="w")
            elif kind == "disconnector":
                for ph in PHASES:
                    px = x + PHASE_IDX[ph] * sp
                    self.line_m(px - 1.0, y, px + 1.0, y, LW["thin"])
                    for dx in (-1.0, 0.0, 1.0):
                        self.sh.circle(self.X(px + dx), self.Y(y), 0.25 * self.s * 2)
                self.text_m(x + sp + 1.2, y, node.get("number", ""), 1.6, anchor="w")
            elif kind == "earthing":
                self.sh.circle(self.X(x), self.Y(y), 0.3 * self.s * 2)
                self.line_m(x, y, x, y + 0.8, LW["thin"])
            elif kind == "transformer":
                self.rect_m(x - 2.5, y - 2.0, x + 2.5, y + 2.0, LW["frame"])
                for i in range(5):
                    self.rect_m(x - 3.3 - i * 0.35, y - 1.5, x - 3.0 - i * 0.35, y + 1.5, LW["dim"])
                self.rect_m(x - 4.0, y - 3.0, x + 4.0, y + 3.0, LW["thin"], dash=[1.5, 1])   # 油流出防止堰
                self.text_m(x, y - 5.0, f"{node.get('number', '')}　{node.get('name', '')}", 2.2, anchor="s")
        # 導体（相 S のカプセルを細線で。相 R/T は省略して見やすく）
        for it in self.layout["items"]:
            for pr in it.get("primitives", []):
                if pr.get("phase") == "S":
                    a, b = pr["a"], pr["b"]
                    self.line_m(a[0], a[1], b[0], b[1], LW["dim"], gray=0.5)

    def gantry(self, x, y, length, along="y"):
        r = 0.6
        for dy in (-length / 2, length / 2):
            self.rect_m(x - r, y + dy - r, x + r, y + dy + r, LW["thin"])
        self.line_m(x, y - length / 2, x, y + length / 2, LW["thin"])

    def gantry_line(self, x1, x2, y):
        self.line_m(x1, y, x2, y, LW["thin"])
        for x in [x1 + i * 8.0 for i in range(int((x2 - x1) / 8.0) + 1)]:
            self.rect_m(x - 0.6, y - 0.6, x + 0.6, y + 0.6, LW["thin"])
        self.text_m(x2 + 2, y, "引留鉄構", 2.0, anchor="w")

    def section(self, topo, ox, oy, s, x_cut=0.0):
        """断面（y-z）。x = x_cut の面で切る（1BK を母線に垂直に切る線）。左が北。"""
        sh = self.sh
        y1 = SITE["fence"][1]; y2 = SITE["fence"][3]

        def Xs(y): return ox + (y2 - y) * s     # 北を左に
        def Zs(z): return oy + z * s

        sh.line(Xs(y2 + 5), Zs(0), Xs(y1 - 5), Zs(0), LW["frame"])
        sh.text(Xs(y2 + 5), Zs(0) + 1.0, "GL ±0", 2.2)
        for yy in range(int(y1 // 10) * 10, int(y2) + 1, 10):
            sh.line(Xs(yy), Zs(0), Xs(yy), Zs(0) - 1.0, LW["dim"])
        nodes = {n["id"]: n for n in topo["nodes"]}
        # 導体（切断面の相）: 中心相 S のカプセルで |x| が小さいもの
        for it in self.layout["items"]:
            node = nodes.get(it["id"]); kv = (node or {}).get("voltage_kv", 220)
            for pr in it.get("primitives", []):
                a, b = pr["a"], pr["b"]
                if pr.get("phase") == "S" and abs(a[0] - x_cut) < 0.6 and abs(b[0] - x_cut) < 0.6:
                    sh.line(Xs(a[1]), Zs(a[2]), Xs(b[1]), Zs(b[2]), LW[kv] if kv in LW else LW["thin"])
        for st in self.layout["structures"]:
            for pr in st["primitives"]:
                a, b = pr["a"], pr["b"]
                if a[0] <= x_cut <= b[0] or b[0] <= x_cut <= a[0]:
                    sh.line(Xs(a[1]) - 1.0, Zs(a[2]), Xs(a[1]) + 1.0, Zs(a[2]), LW["dim"]); sh.circle(Xs(a[1]), Zs(a[2]), 0.5)
                    sh.text(Xs(a[1]) + 1.5, Zs(a[2]) + 0.5, "架空地線", 1.8)
        # 鉄構（引留・母線）: 柱と梁
        for vl in ("220", "66"):
            cfg = P[vl]
            for yg, zg in ((cfg["line_y"][0], cfg["line_z"]), (cfg["line_y"][1], cfg["line_z"]), (cfg["busA"]["y"], cfg["busA"]["z"] + 1.5), (cfg["busB"]["y"], cfg["busB"]["z"] + 1.5)):
                self.lattice(Xs(yg), Zs(0), 1.2 * s, zg * s)
                sh.line(Xs(yg) - 2.5 * s, Zs(zg), Xs(yg) + 2.5 * s, Zs(zg), LW["thin"])
        # 機器（切断面上の開閉器・変圧器）
        for it in self.layout["items"]:
            node = nodes.get(it["id"])
            if node is None or "at" not in it or abs(it["at"][0] - x_cut) > 0.6:
                continue
            x, y, z = it["at"]; kind = node["kind"]
            if kind in ("breaker", "disconnector"):
                w = 1.6 if kind == "breaker" else 1.0
                sh.rect(Xs(y) - w / 2 * s, Zs(0), w * s, 1.6 * s, LW["thin"])                     # 架台
                sh.rect(Xs(y) - 0.3 * s, Zs(1.6), 0.6 * s, (z - 1.6) * s, LW["thin"])            # 碍管
                if kind == "breaker":
                    sh.rect(Xs(y) - 1.2 * s, Zs(z), 2.4 * s, 0.8 * s, LW["thin"])
                sh.text(Xs(y), Zs(z) + 1.2 * s + 1.0, node.get("number", ""), 1.6, angle=90, anchor="sw")
            elif kind == "transformer":
                sh.rect(Xs(y) - 2.5 * s, Zs(0), 5.0 * s, 4.0 * s, LW["frame"])
                for dy, zb, vl in ((2.0, P["220"]["tr_z"], 220), (-2.0, P["66"]["tr_z"], 66)):
                    sh.rect(Xs(y + dy) - 0.25 * s, Zs(4.0), 0.5 * s, (zb + 1.2 - 4.0) * s, LW["thin"])
                sh.text(Xs(y), Zs(0) - 4.0, f"{node.get('number', '')}　{node.get('name', '')}", 2.2, anchor="s")
        # 高さの寸法（右端）と、母線・引留の高さ
        xd = Xs(y1 - 2)
        marks = sorted({P["66"]["eq_z"], P["66"]["busB"]["z"], P["220"]["eq_z"], P["220"]["busB"]["z"], P["66"]["line_z"], P["220"]["busA"]["z"], P["66"]["gw_z"], P["220"]["line_z"], P["220"]["gw_z"]})
        for z in marks:
            sh.line(xd - 2, Zs(z), xd + 2, Zs(z), LW["dim"])
            sh.text(xd + 3, Zs(z), f"▽ GL+{int(z * 1000):,}", 2.0, anchor="w")
        sh.line(xd, Zs(0), xd, Zs(marks[-1]), LW["dim"])
        # 平面方向の寸法（通り芯 Y）
        yd = Zs(0) - 10
        pts = [y2, P["220"]["line_y"][0], P["220"]["busA"]["y"], P["220"]["busB"]["y"], P["220"]["line_y"][1], P["220"]["tr_y"], P["66"]["line_y"][0], P["66"]["busA"]["y"], P["66"]["busB"]["y"], P["66"]["line_y"][1], y1]
        for a, b in zip(pts, pts[1:]):
            sh.dim(Xs(a), yd, Xs(b), yd, f"{int(abs(a - b) * 1000):,}", off=0, size_mm=2.0)
        for lab, y in (("Y1", P["220"]["busA"]["y"]), ("Y2", P["220"]["busB"]["y"]), ("Y3", P["220"]["tr_y"]), ("Y4", P["66"]["busA"]["y"]), ("Y5", P["66"]["busB"]["y"])):
            sh.circle(Xs(y), yd - 8, 3.0); sh.text(Xs(y), yd - 8, lab, 2.5, anchor="c")
        sh.text(ox, Zs(marks[-1]) + 10, "断面図　A－A（X1 通り、1BK を母線に垂直に切る。左が北）　1/400", 3.5)

    def lattice(self, x, y0, w, h):
        self.sh.rect(x - w / 2, y0, w, h, LW["thin"])
        n = max(1, int(h / 4.0))
        for i in range(n):
            ya = y0 + i * h / n; yb = y0 + (i + 1) * h / n
            self.sh.line(x - w / 2, ya, x + w / 2, yb, LW["dim"]); self.sh.line(x - w / 2, yb, x + w / 2, ya, LW["dim"])


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", choices=["jis", "circle"], default="jis", help="単線結線図の図記号（既定 JIS C 0617）")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    font = setup_font()
    topo = json.loads((TRUTH / "topology.json").read_text(encoding="utf-8"))
    layout = json.loads((TRUTH / "layout.json").read_text(encoding="utf-8"))

    # 1) 単線結線図
    sh = Sheet(out / f"{SITE_ID}_sld.pdf", A3, font, "単 線 結 線 図", "S-01-1", "なし")
    SLD(sh, topo, args.symbols).draw(); sh.save()

    # 2) 一般平面図 1/1000（1m = 1mm）
    sh = Sheet(out / f"{SITE_ID}_plan.pdf", A3, font, "一 般 平 面 図", "S-01-2", "1/1,000")
    pl = Plan(sh, layout, 1.0, ox=95.0, oy=165.0)
    pl.surroundings(); pl.fence(); pl.roads_buildings(); pl.equipment_outline()
    sh.north(60, 265); pl.info_table(255, 180)
    sh.text(40, sh.h - 22, "一般平面図", 4.0)
    sh.save()

    # 3) 機械器具装置図（A1）: 平面 1/400 ＋ 断面 1/400
    sh = Sheet(out / f"{SITE_ID}_layout.pdf", A1, font, "機 械 器 具 装 置 図", "S-01-3", "1/400")
    s = 2.5   # 1m = 2.5mm
    ld = LayoutDrawing(sh, layout, s, ox=120.0, oy=395.0)
    ld.fence(); ld.roads_buildings(); ld.grid_lines(); ld.equipment_plan(topo)
    sh.north(75, 545)
    sh.text(45, sh.h - 24, "機械器具装置図（屋外）　平面図 1/400", 4.0)
    sh.line(ld.X(0), ld.Y(SITE["fence"][3]) + 20, ld.X(0), ld.Y(SITE["fence"][1]) - 20, LW["frame"], dash=[6, 2])
    sh.text(ld.X(0) + 1.5, ld.Y(SITE["fence"][3]) + 20, "A", 4.0); sh.text(ld.X(0) + 1.5, ld.Y(SITE["fence"][1]) - 24, "A", 4.0)
    ld.section(topo, ox=455.0, oy=330.0, s=s, x_cut=0.0)
    sh.save()
    print(f"wrote {out}: {SITE_ID}_sld.pdf, {SITE_ID}_plan.pdf, {SITE_ID}_layout.pdf")


if __name__ == "__main__":
    main()
