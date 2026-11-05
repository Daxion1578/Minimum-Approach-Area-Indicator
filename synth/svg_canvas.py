"""reportlab の Canvas と同じ呼び方で SVG を描く小さな代役。

図面（synth/gen_drawings.py の Sheet）は reportlab の Canvas に描いている。画面に同じ図を出すために、
使っている命令だけを同じ名前で持ち、SVG の文字列にする。座標は PDF と同じポイント（左下原点）で受け取り、
SVG（左上原点）へ上下を反転して書く。図の中身は PDF と完全に同じ関数で描かれるので、画面と承認の PDF がずれない。
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape


def _mul(m, n):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2, a * e2 + c * f2 + e, b * e2 + d * f2 + f)


class SvgCanvas:
    def __init__(self, w_pt: float, h_pt: float):
        self.w, self.h = w_pt, h_pt
        self.out: list[str] = []
        self._lw, self._stroke, self._fill, self._dash = 1.0, "#000", "#000", None
        self._font, self._size = "sans-serif", 10.0
        self._m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        self._stack: list[tuple] = []

    # ---- 状態
    def setLineWidth(self, w): self._lw = w
    def setStrokeGray(self, g): self._stroke = _gray(g)
    def setFillGray(self, g): self._fill = _gray(g)
    def setStrokeColorRGB(self, r, g, b): self._stroke = _rgb(r, g, b)
    def setFillColorRGB(self, r, g, b): self._fill = _rgb(r, g, b)
    def setDash(self, d=None, phase=0): self._dash = list(d) if d else None
    def setFont(self, name, size): self._font, self._size = name, size

    def saveState(self):
        self._stack.append((self._lw, self._stroke, self._fill, self._dash, self._font, self._size, self._m))

    def restoreState(self):
        self._lw, self._stroke, self._fill, self._dash, self._font, self._size, self._m = self._stack.pop()

    def translate(self, x, y): self._m = _mul(self._m, (1, 0, 0, 1, x, y))

    def rotate(self, deg):
        r = math.radians(deg)
        self._m = _mul(self._m, (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0))

    # ---- 座標（PDF → SVG）
    def _p(self, x, y):
        a, b, c, d, e, f = self._m
        return (round(a * x + c * y + e, 2), round(self.h - (b * x + d * y + f), 2))

    def _st(self, fill=None):
        dash = f' stroke-dasharray="{",".join(f"{v:g}" for v in self._dash)}"' if self._dash else ""
        return f'stroke="{self._stroke}" stroke-width="{self._lw:g}" fill="{fill or "none"}"{dash}'

    # ---- 図形
    def line(self, x1, y1, x2, y2):
        (a, b), (c, d) = self._p(x1, y1), self._p(x2, y2)
        self.out.append(f'<line x1="{a}" y1="{b}" x2="{c}" y2="{d}" {self._st()}/>')

    def rect(self, x, y, w, h, fill=0, stroke=1):
        pts = [self._p(x, y), self._p(x + w, y), self._p(x + w, y + h), self._p(x, y + h)]
        st = self._st(self._fill if fill else None) if stroke else f'stroke="none" fill="{self._fill}"'
        self.out.append(f'<polygon points="{" ".join(f"{a},{b}" for a, b in pts)}" {st}/>')

    def circle(self, x, y, r, fill=0, stroke=1):
        cx, cy = self._p(x, y)
        st = self._st(self._fill if fill else None) if stroke else f'stroke="none" fill="{self._fill}"'
        self.out.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.2f}" {st}/>')

    def arc(self, x1, y1, x2, y2, startAng=0, extent=90):
        cx, cy, rx, ry = (x1 + x2) / 2, (y1 + y2) / 2, abs(x2 - x1) / 2, abs(y2 - y1) / 2
        pts = []
        for i in range(13):
            t = math.radians(startAng + extent * i / 12)
            pts.append(self._p(cx + rx * math.cos(t), cy + ry * math.sin(t)))
        self.out.append(f'<polyline points="{" ".join(f"{a},{b}" for a, b in pts)}" {self._st()}/>')

    def drawString(self, x, y, s):
        a, b, c, d, e, f = _mul(self._m, (1, 0, 0, 1, x, y))
        # PDF の行列に上下反転をかけ、文字そのものは正立させる: F · M · S(1,-1)
        m = (a, -b, -c, d, e, self.h - f)
        self.out.append(f'<text transform="matrix({m[0]:.4f},{m[1]:.4f},{m[2]:.4f},{m[3]:.4f},{m[4]:.2f},{m[5]:.2f})" '
                        f'font-size="{self._size:.2f}" fill="{self._fill}">{escape(s)}</text>')

    def showPage(self): pass
    def save(self): pass

    def to_svg(self, extra: str = "") -> str:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w:.1f} {self.h:.1f}" '
                f'font-family="\'Noto Sans JP\',\'Hiragino Sans\',\'Yu Gothic\',Meiryo,sans-serif">'
                f'<rect width="100%" height="100%" fill="#fff"/>' + "".join(self.out) + extra + "</svg>")


def _gray(g: float) -> str:
    v = int(round(max(0.0, min(1.0, g)) * 255))
    return f"#{v:02x}{v:02x}{v:02x}"


def _rgb(r, g, b) -> str:
    return "#" + "".join(f"{int(round(max(0.0, min(1.0, v)) * 255)):02x}" for v in (r, g, b))
