"""機械器具装置図（layout.pdf）の描き方の規則。生成側と読む側で共有する一か所。

  生成: synth/gen_drawings.py       この規則どおりに図面を描く
  読む: ingest/pdf_layout.py（予定） 同じ規則を import して、図面の文字・線から機器の位置と高さを逆に求める

ここに置くのは「図面の約束」だけ。機器の寸法は synth/equipment.py、敷地の配置パラメータ P は synth/gen_site.py にある。
P に依存する値（断面の切断位置など）は、P を引数に取る関数 `section_specs(P)` で返す（このモジュールは gen_site を import しない）。

単位: 紙は mm（左下原点）、構内は m（X=東, Y=北, Z=上）、文字高さは mm、線幅は pt。
値は 2026-11 時点の gen_drawings.py と同じ（図面の見た目を変えない）。寸法・名称・番号はすべて仮定値。
"""
from __future__ import annotations

import re

from synth.equipment import EQUIP, LOADS, TRANSFORMER

# --------------------------------------------------------------------------
# 用紙・縮尺・原点
# --------------------------------------------------------------------------
PAPER = "A1"                 # 横置き。reportlab.lib.pagesizes.A1
PLAN_SCALE = 2.5             # 平面 1/400 = 1 m が 2.5 mm
PLAN_OX = 80.0               # 構内 (0,0) の紙上の位置（mm）
PLAN_OY = 150.0

# 断面: 名前 → (縮尺 mm/m, 原点 ox, oy)。原点は「断面の GL の左端（y = y_to）」の紙上位置
#   紙 x = ox + (y_to - y) * scale   （左が北）
#   紙 y = oy + z * scale
SECTION_BASE = {
    "A-A": (2.5, 455.0, 430.0),   # 1/400
    "B-B": (5.0, 455.0, 250.0),   # 1/200
    "C-C": (5.0, 455.0, 70.0),    # 1/200
}
SECTION_ORDER = ("A-A", "B-B", "C-C")
SECTION_SCALE_TEXT = {"A-A": "1/400", "B-B": "1/200", "C-C": "1/200"}


def section_specs(P: dict) -> dict:
    """各断面の仕様。P は synth.gen_site.P。

    cut_axis="x" は「x = cut の面で切り、左が北の y-z 面を見る」。現在の 3 断面はすべてこの向き。
    （y = 一定で切る断面は無いので y_cut は None。増やすときは cut_axis="y" を足す）
    z_top は、その高さより上の高さ寸法を出さない（None なら制限なし）。
    """
    c2, c6 = P["220"], P["66"]
    f = P["site"]["fence"]
    x_cut = c2["banks"][0][1]           # X1 通り（1 号変圧器のベイ）
    x_l1 = c2["lines"][0][2]            # 東線 1L のベイ
    spec = {
        "A-A": dict(x_cut=x_cut, y_cut=None, y_from=f[1], y_to=f[3] + 22, z_top=None,
                    title="断面図　A－A（X1 通り。1BK のベイを母線に垂直に切る。左が北）　1/400"),
        "B-B": dict(x_cut=x_l1, y_cut=None, y_from=c2["bus"]["y"] - 8, y_to=c2["tower"]["y"] + 4, z_top=None,
                    title="断面図　B－B（東線1L ベイ。引留鉄塔から母線まで。左が北）　1/200"),
        "C-C": dict(x_cut=x_cut, y_cut=None, y_from=f[1], y_to=c6["north_gantry"]["y"] + 8, z_top=c6["gw_z"],
                    title="断面図　C－C（X1 通り。66kV ダイヤ D3 を母線に垂直に切る。左が北）　1/200"),
    }
    for name, sp in spec.items():
        s, ox, oy = SECTION_BASE[name]
        sp.update(name=name, scale=s, ox=ox, oy=oy, cut_axis="x", direction="left_is_north",
                  cut=sp["x_cut"], scale_text=SECTION_SCALE_TEXT[name])
    return spec


def section_to_mm(spec: dict, y_m: float, z_m: float) -> tuple[float, float]:
    """断面上の (y, z)（m）→ 紙 (x, y)（mm）。"""
    return spec["ox"] + (spec["y_to"] - y_m) * spec["scale"], spec["oy"] + z_m * spec["scale"]


def section_from_mm(spec: dict, x_mm: float, y_mm: float) -> tuple[float, float]:
    """紙 (x, y)（mm）→ 断面上の (y, z)（m）。section_to_mm の逆。"""
    return spec["y_to"] - (x_mm - spec["ox"]) / spec["scale"], (y_mm - spec["oy"]) / spec["scale"]


def section_paper_box(spec: dict, z_max: float = 32.0) -> tuple[float, float, float, float]:
    """断面が紙の上で占める範囲 (x0, y0, x1, y1)（mm）の目安。読む側が文字をどの断面のものか振り分けるのに使う。
    下は GL（高さラベルは GL より下に出ない）、上は題名の分（+12mm）まで。"""
    x1, _ = section_to_mm(spec, spec["y_from"], 0.0)
    x0, _ = section_to_mm(spec, spec["y_to"], 0.0)
    z_hi = min(z_max, spec["z_top"] + 2.0) if spec["z_top"] else z_max
    return x0 - 12.0, spec["oy"] - 2.0, x1 + 40.0, spec["oy"] + z_hi * spec["scale"] + 12.0


# --------------------------------------------------------------------------
# 向き（機器 id → 軸方向とパンタ型）
# --------------------------------------------------------------------------
def orientation(node_id: str) -> dict:
    """機器 id から平面での向きを決める。

    along: 電流の流れる向き。"x"（母線上のセクション断路器 220-SEC-*）または "y"（ベイの機器列）。
    panto: パンタグラフ形断路器か（220kV の母線側断路器 220-*-BLS。母線の真下に 1 相ずつ置く）。

    web/equipment3d.js の次の判定と同じ規則（ここが元。片方を変えたらもう片方も直す）:
        const panto = kv === 220 && it.id.endsWith('-BLS');
        const alongX = it.id.startsWith('220-SEC');
    """
    return {"along": "x" if node_id.startswith("220-SEC") else "y",
            "panto": node_id.startswith("220-") and node_id.endswith("-BLS")}


# --------------------------------------------------------------------------
# 母線の描き方
# --------------------------------------------------------------------------
BUS_LINEWIDTH_PT = {220: 1.3, 66: 0.9}      # 1/400 平面での母線（相ごとの太線）の線幅。電圧階級で変える
# 母線の本数と番号。220kV は単母線（3 区間 A・B・C をまとめて 1 号）、66kV は 1・1/2 母線の 1号・2号
BUSES = {
    220: [{"no": 1, "plan_key": "bus", "nodes": ("220-BUS-A", "220-BUS-B", "220-BUS-C"), "plan_text": "220kV 母線"}],
    66: [{"no": 1, "plan_key": "busA", "nodes": ("66-BUS-A",), "plan_text": "66kV 1号母線"},
         {"no": 2, "plan_key": "busB", "nodes": ("66-BUS-B",), "plan_text": "66kV 2号母線"}],
}


def bus_label(kv: int, no: int) -> str:
    """断面の高さラベルに使う母線の名前。例 "220kV 1号母線"。"""
    return f"{kv}kV {no}号母線"


def bus_of_node(node_id: str) -> tuple[int, int] | None:
    """母線ノード id → (電圧 kV, 号)。母線でなければ None。"""
    for kv, lst in BUSES.items():
        for b in lst:
            if node_id in b["nodes"]:
                return kv, b["no"]
    return None


# --------------------------------------------------------------------------
# 機器番号の文字の置き方（装置図の平面）
# --------------------------------------------------------------------------
# 文字はすべて「左下基準（baseline の左端）」で描く。機器中心 at（m）から文字の左下までのオフセットを
# 記号の種類ごとに持つ。紙 mm = PLAN_O + at * PLAN_SCALE + (dx, dy)。
_BASE_DY = -1.0 / 2.8       # 旧実装の anchor="w"（文字の縦中央）を左下基準に直す分: -size/2.8 を高さ 1mm あたりで


def symbol_kind(node_kind: str, voltage_kv: int, node_id: str) -> str:
    """トポロジーの kind・電圧・id → 記号の種類（番号文字の置き方を決めるキー）。
    "ds_220" "ds_66" "ds_panto_220" "cb_220" "cb_66" "earthing" "transformer" "load_SC" "load_SR"。"""
    if node_kind == "disconnector":
        return ("ds_panto_" if orientation(node_id)["panto"] else "ds_") + str(voltage_kv)
    if node_kind == "breaker":
        return f"cb_{voltage_kv}"
    if node_kind == "load":
        return "load_SC" if "SC" in node_id else "load_SR"
    if node_kind in ("earthing", "transformer"):
        return node_kind
    raise ValueError(f"番号を描かない種類: {node_kind}")


NUMBER_TEXT_HEIGHT_MM = {
    "ds_220": 1.6, "ds_66": 1.6, "ds_panto_220": 1.6, "cb_220": 1.6, "cb_66": 1.6,
    "earthing": 1.4, "transformer": 2.2, "load_SC": 1.8, "load_SR": 1.8,
}

_CENTER_FIX_MM = 2.5     # 旧実装で文字を中央揃え（anchor="s"）にしていた分の概算（半幅）。左下基準に直したので固定値で代用


def _offset_mm(kind: str, along: str = "y") -> tuple[float, float]:
    s = PLAN_SCALE
    h = NUMBER_TEXT_HEIGHT_MM[kind]
    dy0 = _BASE_DY * h
    if kind.startswith("ds_panto_"):
        sp = EQUIP[int(kind.split("_")[-1])]["phase_sp"]
        return (sp + 1.0) * s, -sp * s + dy0                     # S 相（中央）の隣り、1 相ぶん手前（南）
    if kind.startswith("ds_"):
        kv = int(kind.split("_")[-1]); e = EQUIP[kv]["ds"]; sp = EQUIP[kv]["phase_sp"]
        if along == "x":
            return -_CENTER_FIX_MM, (sp + 1.0) * s               # 相の北側
        return (sp + e["frame_w"]) * s, dy0                      # 最も東の相の右
    if kind.startswith("cb_"):
        kv = int(kind.split("_")[-1]); e = EQUIP[kv]["cb"]; sp = EQUIP[kv]["phase_sp"]
        cw = e["cabinet"][0]
        return (sp + e["tank_d"] / 2 + cw + 0.4) * s, dy0       # 操作箱の右
    if kind == "earthing":
        return 1.8, -0.5                                         # 接地記号（半径 0.5m）の右
    if kind == "transformer":
        return -_CENTER_FIX_MM - 1.0, (-TRANSFORMER["bund"][1] / 2 - 1.5) * s   # 油流出防止堰の南側
    if kind.startswith("load_"):
        return -4.0, (LOADS[kind[5:]]["size"][1] / 2 + 0.5) * s       # 据付寸法の北側
    raise ValueError(kind)


def number_text_height(kind: str) -> float:
    return NUMBER_TEXT_HEIGHT_MM[kind]


def number_text_anchor(kind: str, at_xy_m, along: str = "y") -> tuple[float, float]:
    """機器中心 at（構内 m）→ 機器番号の文字の左下（紙 mm）。"""
    dx, dy = _offset_mm(kind, along)
    return PLAN_OX + at_xy_m[0] * PLAN_SCALE + dx, PLAN_OY + at_xy_m[1] * PLAN_SCALE + dy


def center_from_text(kind: str, text_xy_mm, along: str = "y") -> tuple[float, float]:
    """number_text_anchor の逆。文字の左下（紙 mm）→ 機器中心（構内 m）。"""
    dx, dy = _offset_mm(kind, along)
    return (text_xy_mm[0] - dx - PLAN_OX) / PLAN_SCALE, (text_xy_mm[1] - dy - PLAN_OY) / PLAN_SCALE


# --------------------------------------------------------------------------
# 断面の高さラベル
# --------------------------------------------------------------------------
HEIGHT_LABEL_SIZE_MM = (1.4, 1.6)     # 文字高さの範囲（読みやすさのため小さく）
HEIGHT_LABEL_RE = re.compile(r"^(?P<id>.+?) GL\+(?P<mm>\d{1,3}(?:,\d{3})*|\d+)$")


def height_label(element_id: str, z_m: float) -> str:
    """"{element_id} GL+{z_mm:,}"。例 "6T-110 GL+4,000"、"220kV 1号母線 GL+10,500"。"""
    return f"{element_id} GL+{round(z_m * 1000):,}"


def parse_height_label(text: str) -> tuple[str, float] | None:
    """height_label の逆。高さラベルでなければ None。
    断面右端の高さ寸法（"▽ GL+10,500"）は要素名が無いので None を返す。"""
    m = HEIGHT_LABEL_RE.match(text.strip())
    if not m or m.group("id").startswith("▽"):
        return None
    return m.group("id"), int(m.group("mm").replace(",", "")) / 1000.0
