#!/usr/bin/env python3
"""
合成変電所の図面（ベクター PDF）を生成する。

  python3 proto/tools/gen_drawings.py            # proto/data/drawings/ に3枚
  配置図   SITE-01_plan.pdf     平面（x-y）1:500
  断面図   SITE-01_section.pdf  D2 ベイの y-z 断面 1:250、高さの寸法付き
  単線結線図 SITE-01_sld.pdf    系統図（縮尺なし）

文字はすべて PDF のテキストとして入る（画素ではない）ので、あとで線と文字を取り出して
候補グラフを作る試験に使える。寸法・名称は全部架空の仮定値。
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL = ROOT / "data" / "substation_fictional.json"
OUT = ROOT / "data" / "drawings"
MM = 72 / 25.4

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
]


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
    """A3 横の図面。model 座標(m) → 紙(pt) の変換と、表題欄・枠を持つ。"""

    def __init__(self, path, title, scale_text, font, x0, y0, scale_mm_per_m, origin_mm=(40, 40), axes=("x", "y")):
        self.c = canvas.Canvas(str(path), pagesize=landscape(A3))
        self.w, self.h = landscape(A3)
        self.font = font
        self.x0, self.y0, self.s = x0, y0, scale_mm_per_m
        self.ox, self.oy = origin_mm
        self.axes = axes
        self.c.setLineWidth(0.8)
        self.c.rect(10 * MM, 10 * MM, self.w - 20 * MM, self.h - 20 * MM)
        self.title_block(title, scale_text)

    # model(m) -> page(pt)
    def P(self, a, b):
        return ((self.ox + (a - self.x0) * self.s) * MM, (self.oy + (b - self.y0) * self.s) * MM)

    def line(self, a1, b1, a2, b2, width=0.5, dash=None, gray=0.0):
        self.c.setLineWidth(width); self.c.setStrokeGray(gray)
        self.c.setDash(dash or [])
        x1, y1 = self.P(a1, b1); x2, y2 = self.P(a2, b2)
        self.c.line(x1, y1, x2, y2)
        self.c.setDash([])

    def poly(self, pts, width=0.5, gray=0.0):
        for (a1, b1), (a2, b2) in zip(pts, pts[1:]):
            self.line(a1, b1, a2, b2, width, gray=gray)

    def text(self, a, b, s, size=6, angle=0, anchor="sw", gray=0.0):
        x, y = self.P(a, b)
        self.c.saveState(); self.c.setFillGray(gray); self.c.setFont(self.font, size)
        self.c.translate(x, y); self.c.rotate(angle)
        tw = pdfmetrics.stringWidth(s, self.font, size)
        # anchor: sw=左下基準, s=中央下, se=右下, c=中央
        dx = {"sw": 0.0, "s": -tw / 2, "se": -tw, "c": -tw / 2}[anchor]
        dy = -size / 2.8 if anchor == "c" else 0.0
        self.c.drawString(dx, dy, s); self.c.restoreState()

    def rect(self, a, b, wa, hb, width=0.5, fill=False):
        x, y = self.P(a, b); self.c.setLineWidth(width); self.c.setStrokeGray(0)
        self.c.rect(x - wa * self.s * MM / 2, y - hb * self.s * MM / 2, wa * self.s * MM, hb * self.s * MM, fill=fill)

    def circle(self, a, b, r_m, width=0.5):
        x, y = self.P(a, b); self.c.setLineWidth(width); self.c.circle(x, y, r_m * self.s * MM)

    def dim(self, a1, b1, a2, b2, label, offset_m=1.5, size=6):
        """寸法線（垂直または水平）。label は数字の文字列（mm）。"""
        if abs(a1 - a2) < 1e-6:  # 垂直
            ao = a1 + offset_m
            self.line(a1, b1, ao + 0.5, b1, 0.3); self.line(a1, b2, ao + 0.5, b2, 0.3)
            self.line(ao, b1, ao, b2, 0.3)
            self.text(ao + 0.3, (b1 + b2) / 2, label, size, angle=90, anchor="s")
        else:
            bo = b1 + offset_m
            self.line(a1, b1, a1, bo + 0.5, 0.3); self.line(a2, b2, a2, bo + 0.5, 0.3)
            self.line(a1, bo, a2, bo, 0.3)
            self.text((a1 + a2) / 2, bo + 0.3, label, size, anchor="s")

    def title_block(self, title, scale_text):
        c = self.c; x = self.w - 10 * MM - 120 * MM; y = 10 * MM
        c.setLineWidth(0.8); c.rect(x, y, 120 * MM, 30 * MM)
        c.setFont(self.font, 11); c.drawString(x + 4 * MM, y + 21 * MM, title)
        c.setFont(self.font, 7)
        c.drawString(x + 4 * MM, y + 14 * MM, "合成変電所 SITE-01（架空。寸法・名称はすべて仮定値）")
        c.drawString(x + 4 * MM, y + 9 * MM, f"縮尺 {scale_text}　単位 mm　座標 X=東 Y=北 Z=上")
        c.drawString(x + 4 * MM, y + 4 * MM, "図番 SITE-01-DRW　生成 proto/tools/gen_drawings.py")

    def save(self):
        self.c.showPage(); self.c.save()


# --------------------------------------------------------------------------
def plan(model, font):
    sh = Sheet(OUT / "SITE-01_plan.pdf", "配置図（平面）", "1:500", font, x0=-15, y0=-118, scale_mm_per_m=2.0, origin_mm=(30, 20))
    # 座標グリッド（10m）
    for x in range(-10, 71, 10):
        sh.line(x, -118, x, 12, 0.2, dash=[1, 2], gray=0.6); sh.text(x, 13, f"X={x}", 5, anchor="s", gray=0.4)
    for y in range(-110, 11, 10):
        sh.line(-15, y, 72, y, 0.2, dash=[1, 2], gray=0.6); sh.text(-16, y, f"Y={y}", 5, anchor="se", gray=0.4)
    # 導体（平面投影）
    for cnd in model["conductors"]:
        pts = [(p[0], p[1]) for p in cnd["polyline"]]
        w = 1.2 if cnd["type"] == "bus" else 0.5
        sh.poly(pts, w)
    # 母線のラベル
    for n in model["nodes"]:
        if n["kind"] == "bus":
            vl = n["voltage"]; busid = n["id"]
            cs = [c for c in model["conductors"] if c["node"] == busid and c["type"] == "bus"]
            if cs:
                c0 = cs[0]; sh.text(c0["polyline"][0][0] - 1, c0["polyline"][0][1] + 0.6, n["name"], 7, anchor="se")
                for c in cs:
                    sh.text(c["polyline"][1][0] + 0.5, c["polyline"][1][1] - 0.3, c["phase"], 5)
    # 架空地線
    for s in model["structures"]:
        pts = [(p[0], p[1]) for p in s["polyline"]]
        for (a1, b1), (a2, b2) in zip(pts, pts[1:]):
            sh.line(a1, b1, a2, b2, 0.4, dash=[3, 1.5])
        sh.text(pts[0][0], pts[0][1] + 0.5, s.get("name", s["id"]) + f"（高さ {s['polyline'][0][2]:.0f}m）", 5)
    # 開閉器・接地・変圧器
    for s in model["switches"]:
        if "position" not in s:
            continue
        x, y, _ = s["position"]
        if s["kind"] == "CB":
            sh.rect(x, y, 1.6, 1.6, 0.6)
        else:
            sh.rect(x, y, 1.2, 0.8, 0.4)
        sh.text(x + 1.0, y - 0.3, s["id"], 4)
    for e in model["earth_switches"]:
        if "position" not in e:
            continue
        x, y, _ = e["position"]; sh.circle(x, y, 0.35, 0.4); sh.text(x + 0.5, y - 0.9, e["id"], 3.5, gray=0.3)
    for t in model["transformers"]:
        x, y, _ = t["position"]; sh.rect(x, y, 8, 5, 0.8); sh.text(x, y, t["name"], 6, anchor="c")
    # ベイ名
    for vl in ("220", "66"):
        for n in model["nodes"]:
            pass
    bays = {}
    for s in model["switches"]:
        if s.get("bay") and "position" in s and s["id"].endswith("_LSA"):
            bays[s["id"].rsplit("_", 1)[0]] = s["position"]
    for bay, (x, y, _) in bays.items():
        sh.text(x, y + 4.5, bay.replace("_", "kV "), 7, anchor="s")
    # 凡例・方位・スケール
    sh.text(-10, -56, "凡例：太線 母線　細線 導体　□ 遮断器(CB)　▭ 断路器(LS)　○ 接地開閉器(ES)　破線 架空地線", 6)
    sh.text(-10, -59, "N ↑（Y＋が北）", 7)
    sh.line(-10, -62, 0, -62, 1.2); sh.text(-10, -64.5, "0", 5); sh.text(0, -64.5, "10 m", 5)
    sh.save()


def section(model, font):
    cfg = {"xbay": 18.0, "busA": (0.0, 10.5), "busB": (-36.0, 6.5), "eq_z": 5.0, "gw": ((8.0, 25.0), (-44.0, 25.0)), "sp": 4.0}
    sh = Sheet(OUT / "SITE-01_section.pdf", "断面図（220kV D2 ベイ、A-A 断面）", "1:250", font, x0=-52, y0=-4, scale_mm_per_m=4.0, origin_mm=(25, 45), axes=("y", "z"))
    # 地面
    sh.line(-52, 0, 16, 0, 1.0); sh.text(14, 0.5, "GL ±0", 6, anchor="se")
    for y in range(-50, 16, 10):
        sh.line(y, 0, y, -1, 0.3); sh.text(y, -2.2, f"Y={y}", 5, anchor="s")
    # 母線（3相を y にずらして ○ で表す。断面なので導体は点）
    for name, (yb, zb) in (("A母線", cfg["busA"]), ("B母線", cfg["busB"])):
        for ph, k in (("R", -1), ("S", 0), ("T", 1)):
            yy = yb - k * cfg["sp"]
            sh.circle(yy, zb, 0.25, 0.8); sh.text(yy + 0.4, zb + 0.4, f"{name} {ph}相", 5)
        # 碍子・鉄構（簡略）
        sh.line(yb - 6, zb - 1.0, yb + 6, zb - 1.0, 0.8); sh.line(yb - 6, zb - 1.0, yb - 6, 0, 0.8); sh.line(yb + 6, zb - 1.0, yb + 6, 0, 0.8)
        sh.text(yb + 6.3, 1, "鉄構", 5, angle=90)
    # 機器列（端子高さ eq_z に水平導体、下に機器）
    ys = [-6, -9, -12, -15, -18, -21, -24, -27, -30]
    names = ["LSA", "CB1", "LS1B", "LS2A", "CB2", "LS2B", "LS3A", "CB3", "LSB"]
    sh.line(-30, cfg["eq_z"], -6, cfg["eq_z"], 0.6)
    for y, nm in zip(ys, names):
        cb = nm.startswith("CB")
        wdt, hgt = (1.6, 4.0) if cb else (1.0, 3.5)
        sh.rect(y, cfg["eq_z"] / 2 + (0.2 if cb else 0.0), wdt, hgt, 0.6)
        sh.text(y, 0.4, f"220_D2_{nm}", 4, angle=90)
    # 母線ドロッパー
    for (yb, zb) in (cfg["busA"], cfg["busB"]):
        yy = yb  # S相の位置で代表
        end = -6 if zb > 8 else -30
        sh.line(yy, zb, yy, cfg["eq_z"], 0.5); sh.line(yy, cfg["eq_z"], end, cfg["eq_z"], 0.5)
    # 架空地線と引止め鉄構
    for (yg, zg) in cfg["gw"]:
        sh.circle(yg, zg, 0.2, 0.6); sh.text(yg + 0.5, zg + 0.5, "架空地線", 5)
        sh.line(yg, 0, yg, zg + 1.0, 1.0); sh.text(yg + 0.6, 2, "引止め鉄構", 5, angle=90)
    # 引込線（北側 T1 回路）：機器列から立ち上がって北の鉄構へ
    sh.line(-13.5, cfg["eq_z"], -13.5, 16.0, 0.5); sh.line(-13.5, 16.0, 8.0, 20.0, 0.5); sh.text(-4, 19, "Fable線1L 引込", 5)
    # 寸法
    sh.dim(12, 0, 12, cfg["busA"][1], "10500", offset_m=1.5)
    sh.dim(12, 0, 12, cfg["gw"][0][1], "25000", offset_m=4.5)
    sh.dim(-50, 0, -50, cfg["busB"][1], "6500", offset_m=1.5)
    sh.dim(-50, 0, -50, cfg["gw"][1][1], "25000", offset_m=4.5)
    sh.dim(-3, 0, -3, cfg["eq_z"], "5000", offset_m=0.8)
    sh.dim(cfg["busA"][0] - 4, 13, cfg["busA"][0], 13, "4000", offset_m=0.5)
    sh.dim(-36, 9, 0, 9, "36000", offset_m=0.5)
    sh.text(-50, 28, "注記：対地絶縁距離（設計値）2600。寸法は架空変電所の仮定値。", 6)
    sh.text(-50, 26.5, "断面位置 A-A：X=18000（D2 ベイ中心、S相）", 6)
    sh.save()


def sld(model, font):
    """単線結線図。縮尺なし。横方向にベイ、縦に母線。"""
    sh = Sheet(OUT / "SITE-01_sld.pdf", "単線結線図", "なし", font, x0=0, y0=0, scale_mm_per_m=1.0, origin_mm=(20, 20))
    # 紙上の座標を「m」のまま mm として使う（scale 1）
    def yard(vl, y_top, y_bot, x_start, pitch, bays):
        sh.line(x_start - 10, y_top, x_start + pitch * (len(bays) - 1) + 10, y_top, 1.5); sh.text(x_start - 12, y_top + 1, f"{vl}kV A母線", 7, anchor="se")
        sh.line(x_start - 10, y_bot, x_start + pitch * (len(bays) - 1) + 10, y_bot, 1.5); sh.text(x_start - 12, y_bot + 1, f"{vl}kV B母線", 7, anchor="se")
        for i, bay in enumerate(bays):
            x = x_start + i * pitch
            pre = f"{vl}_{bay}"
            seq = [("LSA", "LS"), ("CB1", "CB"), ("LS1B", "LS"), ("T1", "tap"), ("LS2A", "LS"), ("CB2", "CB"), ("LS2B", "LS"), ("T2", "tap"), ("LS3A", "LS"), ("CB3", "CB"), ("LSB", "LS")]
            n = len(seq); step = (y_top - y_bot) / (n + 1)
            sh.line(x, y_top, x, y_bot, 0.6)
            for j, (nm, kind) in enumerate(seq):
                y = y_top - (j + 1) * step
                if kind == "CB":
                    sh.rect(x, y, 4, 4, 0.8, fill=False); sh.text(x + 3, y - 1, f"{pre}_{nm}", 4)
                elif kind == "LS":
                    sh.c.setFillGray(1); sh.rect(x, y, 2.5, 2.5, 0.6, fill=True); sh.c.setFillGray(0)
                    sh.line(x - 1.5, y - 1.5, x + 1.5, y + 1.5, 0.6); sh.text(x + 2.5, y - 1, f"{pre}_{nm}", 4)
                else:
                    tap = f"{pre}_{nm}"
                    circ = next((c for c in model["switches"] if c["from"] == tap and c["id"].endswith("_LS") and "_D" not in c["id"]), None)
                    sw = next((s for s in model["switches"] if s["from"] == tap and s["id"] not in (f"{pre}_LS2A", f"{pre}_LS3A")), None)
                    dx = -14 if nm == "T1" else 14
                    sh.line(x, y, x + dx, y, 0.6)
                    # 接地開閉器
                    sh.line(x + dx / 3, y, x + dx / 3, y - 3, 0.5); sh.line(x + dx / 3 - 1.5, y - 3, x + dx / 3 + 1.5, y - 3, 0.8); sh.line(x + dx / 3 - 0.8, y - 3.8, x + dx / 3 + 0.8, y - 3.8, 0.6)
                    sh.text(x + dx / 3 + 0.5, y - 5.5, f"{pre}_{nm}_ES", 3.5, gray=0.3)
                    if sw is None:
                        sh.text(x + dx, y + 1, "（新設予定）", 5, anchor="s" if dx > 0 else "se")
                        continue
                    name = sw.get("name", sw["id"])
                    if "線路" in name:
                        # 線路：断路器→矢印
                        sh.c.setFillGray(1); sh.rect(x + dx * 0.6, y, 2.5, 2.5, 0.6, fill=True); sh.c.setFillGray(0)
                        sh.line(x + dx * 0.6 - 1.5, y - 1.5, x + dx * 0.6 + 1.5, y + 1.5, 0.6)
                        sh.text(x + dx * 0.6 + (1 if dx > 0 else -1), y + 2, sw["id"], 3.5, anchor="sw" if dx > 0 else "se")
                        tip = x + dx + (6 if dx > 0 else -6)
                        sh.line(x + dx, y, tip, y, 0.6); sh.line(tip, y, tip - (2 if dx > 0 else -2), y + 1.2, 0.6); sh.line(tip, y, tip - (2 if dx > 0 else -2), y - 1.2, 0.6)
                        sh.text(tip + (1 if dx > 0 else -1), y - 1, name.replace(" 線路断路器", ""), 6, anchor="sw" if dx > 0 else "se")
                    else:
                        # 変圧器：二重円
                        cx = x + dx + (5 if dx > 0 else -5)
                        sh.c.setFillGray(1); sh.rect(x + dx * 0.6, y, 2.5, 2.5, 0.6, fill=True); sh.c.setFillGray(0)
                        sh.line(x + dx * 0.6 - 1.5, y - 1.5, x + dx * 0.6 + 1.5, y + 1.5, 0.6)
                        sh.text(x + dx * 0.6 + (1 if dx > 0 else -1), y + 2, sw["id"], 3.5, anchor="sw" if dx > 0 else "se")
                        sh.circle(cx, y + 1.5, 2.5, 0.8); sh.circle(cx, y - 1.5, 2.5, 0.8)
                        sh.text(cx + 3.5, y - 1, name.replace(" 断路器", ""), 5)
            sh.text(x, y_top + 3, f"{vl}kV {bay}", 7, anchor="s")

    yard("220", 240, 150, 40, 70, ["D1", "D2", "D3", "D4"])
    yard("66", 110, 30, 40, 60, ["D1", "D2", "D3", "D4"])
    sh.text(20, 128, "1号・2号変圧器 300MVA 220/66kV（一次は 220kV D1/D2 南側、二次は 66kV D1/D2 南側に接続）", 6)
    sh.text(20, 123, "記号：□ 遮断器　斜線付き小四角 断路器　二重円 変圧器　接地記号 接地開閉器　矢印 線路", 6)
    sh.save()


def main():
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    font = setup_font()
    plan(model, font); section(model, font); sld(model, font)
    for p in sorted(OUT.glob("*.pdf")):
        print(f"wrote {p} ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
