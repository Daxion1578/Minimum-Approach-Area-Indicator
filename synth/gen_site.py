#!/usr/bin/env python3
"""合成変電所 SITE-01（全屋外気中、220kV 単母線・66kV 1・1/2 母線、変圧器 3 バンク）の生成。

配置は全屋外気中変電所の一般的な標準配置に倣う（仮定値。実在設備・特定事業者の値ではない）:
  - 敷地 135m × 125m。北に 220kV 配開、中央に変圧器 3 バンクの列と構内道路、南に 66kV 配開、東に建屋
  - 220kV: 単母線（セクション LS 2 台で 3 区間）。送電線 2 回線は母線の北側、変圧器 3 バンクは南側
  - 66kV: 1・1/2 母線 6 ダイヤ。北側回路は変圧器二次 3 ＋ 調相設備（SC・SR）、南側回路は送電線 5。D6 は新設予定
パラメータ P を変えて再生成すれば別の構内になる。

出力（契約の形）:
  data/sites/SITE-01/truth/topology.json   §6.1 図面の構造
  data/sites/SITE-01/truth/layout.json     §6.2 配置（カプセル）
  data/sites/SITE-01/truth/states/*.json   §6.3 開閉器の状態（通常／停止例）

使い方:
  python -m synth.gen_site                 # data/sites/SITE-01 に出力
  python -m synth.gen_site path/to/dir

命名の約束（IDは英数字と - のみ。図面に書く開閉器番号は別途 number に持つ）:
  220-BUS-A / -B / -C         220kV 単母線の 3 区間（bus）。220-SEC-AB / -BC はセクション LS
  220-L<n>-LS / -CB / -BLS    220kV 線路ベイ: 線路断路器・遮断器・母線側断路器。区間は 220-L<n>-N1 / -N2
  220-T<n>-BLS / -CB / -LS    220kV 変圧器ベイ: 母線側断路器・遮断器・機器側断路器。区間は 220-T<n>-N1 / -N2
  66-BUS-A / -B               66kV 1・1/2 の 1号・2号母線（bus）
  66-D<n>-LSA … -LSB          ダイヤの開閉器（disconnector / breaker）
  66-D<n>-N1 … -N6, -T1/-T2   開閉器間の区間と引出点（terminal）
  <kV>-LINE-<符号>            線路（source）。名前は「東線1L」など
  66-SC-1 / 66-SR-1           調相設備（load）
  TR-<n>                      変圧器（transformer）。端子は TR-n.hv / TR-n.lv
  <kV>-TR-<n>-HV / -LV        変圧器ブッシング側の区間（terminal）
  *-ES                        接地開閉器（earthing）。attached_to に接地する区間
"""
from __future__ import annotations

import json
import pathlib
import sys

from synth.equipment import EQUIP, GANTRY, LINE_GANTRY_220, LOADS, TOWER_220, TRANSFORMER

SITE_ID = "SITE-01"
GENERATED_BY = "synth/gen_site.py"

# --------------------------------------------------------------------------
# パラメータ（仮定値）。座標は構内ローカル: X=東, Y=北, Z=上。原点は敷地の南西隅
# --------------------------------------------------------------------------
P = {
    "name": "合成変電所 SITE-01（全屋外気中、220kV 単母線・66kV 1・1/2 母線、変圧器 3 バンク）",
    "site": {
        "fence": (0.0, 0.0, 135.0, 125.0),          # 外柵 x_min, y_min, x_max, y_max
        "building": (108.0, 66.0, 122.0, 80.0),     # 本館 14m×14m（東側）
        "roads": [(8.0, 57.0, 128.0, 63.0),          # 構内道路 幅 6m: 変圧器列の南を東西に
                  (122.0, 8.0, 128.0, 57.0),         # 東側を南北に（入口へ）
                  (8.0, 63.0, 14.0, 104.0),          # 西側を北へ
                  (128.0, 8.0, 135.0, 14.0)],        # 入口（南東）
        "tank": (100.0, 40.0),                      # 碍洗用水槽
        "oil_sep": (24.0, 65.0),                    # 油水分離槽
    },
    "220": {
        "kv": 220, "code": "20",
        "phase_sp": 4.0,            # 相間（仮定値。220kV の一般的な標準離隔）
        "bus": {"y": 96.0, "z": 10.5, "x0": 22.0, "x1": 114.0},
        "sections": [("A", 54.0), ("B", 82.0)],     # セクション LS の x（A|B, B|C）
        "eq_z": EQUIP[220]["terminal_z"],   # 機器端子高さ（synth/equipment.py）
        "line_gantry": {"y": 121.0, "z": LINE_GANTRY_220["beam"], "column": LINE_GANTRY_220["column"]}, "gw_z": LINE_GANTRY_220["column"],
        "tower": {"y": 142.0, "z": TOWER_220["attach_z"], "height": TOWER_220["height"]},   # 構外の引留鉄塔
        "cb_z": EQUIP[220]["cb_terminal_z"],
        "line_bay": {"la": 117.5, "ls": 114.0, "cb": 108.0},   # 線路ベイの y（北→南）。CT は遮断器のブッシング根元。母線側断路器は母線直下
        "tr_bay": {"cb": 87.0, "ls": 80.0, "la": 76.0},        # 変圧器ベイの y（北→南）。CT は遮断器のブッシング根元。母線側断路器は母線直下
        "tr_y": 69.0, "tr_z": TRANSFORMER["hv"]["top_z"],   # 変圧器タンク中心 y・一次ブッシング端子高さ
        "lines": [("E1", "東線1L", 40.0, "A"), ("E2", "東線2L", 96.0, "C")],   # (符号, 名前, x, 区間)
        "banks": [(1, 48.0, "A"), (2, 76.0, "B"), (3, 104.0, "C")],           # (番号, x, 区間)。線路ベイから 8m 東（パンタ型断路器の柱が重ならないように）
    },
    "66": {
        "kv": 66, "code": "6",
        "phase_sp": 1.5, "bay_pitch": 7.0,          # 仮定値。66kV の一般的な標準離隔・スパン
        "busA": {"y": 44.0, "z": 6.5}, "busB": {"y": 14.0, "z": 4.5},
        "eq_z": EQUIP[66]["terminal_z"], "gw_z": 14.0, "tr_lv_z": TRANSFORMER["lv"]["top_z"],
        "north_gantry": {"y": 50.0, "z": 10.0},     # 変圧器二次・調相の引留
        "line_gantry": {"y": 4.0, "z": 10.0},       # 送電線の引留（南）
        "load_y": 54.0,                             # 調相設備の据付 y
        "x0": 34.0,
        "bays": [
            # (ダイヤID, 北側回路, 南側回路)。回路は ("line", 符号, 名前) / ("tr", 番号, 名前) / ("load", 符号, 名前)
            ("D1", ("tr", 1, "1号変圧器 二次"), ("line", "S1", "南線1L")),
            ("D2", ("tr", 2, "2号変圧器 二次"), ("line", "S2", "南線2L")),
            ("D3", ("tr", 3, "3号変圧器 二次"), ("line", "P1", "港線1L")),
            ("D4", ("load", "SC1", "#1SC"), ("line", "P2", "港線2L")),
            ("D5", ("load", "SR1", "#1SR"), ("line", "H1", "浜線1L")),
            ("D6", None, None),  # 新設予定（母線は延長済み、機器未接続）
        ],
    },
}

PHASES = ["R", "S", "T"]
PHASE_IDX = {"R": -1, "S": 0, "T": 1}
COND_R = 0.02   # 導体半径（m）
BUS_R = 0.03


def r3(p):
    return [round(float(v), 3) for v in p]


class Site:
    def __init__(self, name: str):
        self.topo = {
            "schema_version": "0.1", "site_id": SITE_ID, "generated_by": GENERATED_BY, "name": name,
            "notes": ["合成データ。実在の設備・事業者・図面とは無関係。", "寸法・構成・番号はすべて仮定値。"],
            "nodes": [], "edges": [], "questions": [],
        }
        self.layout = {
            "schema_version": "0.1", "site_id": SITE_ID, "generated_by": GENERATED_BY,
            "origin_note": "基準点 P1 = 敷地の南西隅, X=東, Y=北, Z=上（仮定）",
            "notes": ["全寸法は仮定値。架空地線の高さは雷遮蔽設計で決まるため、ここでは仮定。"],
            "reference_points": [{"id": "P1", "x": 0.0, "y": 0.0, "z": 0.0}, {"id": "P2", "x": 135.0, "y": 0.0, "z": 0.0}],
            "items": [], "structures": [],
        }
        self._items: dict[str, dict] = {}
        self._tr: dict[int, dict] = {}
        self.normal_switches: dict[str, str] = {}
        self.sources: list[str] = []

    # ---- topology の基本要素 ----
    def node(self, nid, kind, kv=None, name=None, bay=None, **extra):
        d = {"id": nid, "kind": kind}
        if kv is not None:
            d["voltage_kv"] = kv
        if name:
            d["name"] = name
        if bay:
            d["bay"] = bay
        d.update({k: v for k, v in extra.items() if v is not None})
        self.topo["nodes"].append(d)
        return nid

    def switch(self, sid, kind, kv, normal, name=None, bay=None, at=None, number=None):
        self.node(sid, kind, kv, name, bay, number=number)
        self.normal_switches[sid] = normal
        if at is not None:
            self.item(sid, at=at)
        return sid

    def es(self, eid, attached_to, kv, name=None, at=None, number=None):
        self.node(eid, "earthing", kv, name, attached_to=attached_to, number=number)
        self.normal_switches[eid] = "open"
        if at is not None:
            self.item(eid, at=at)
        return eid

    def edge(self, a, b, conductor="bare", eid=None):
        eid = eid or f"{a.replace('.', '-')}--{b.replace('.', '-')}"
        self.topo["edges"].append({"id": eid, "from": a, "to": b, "conductor": conductor})
        return eid

    # ---- layout ----
    def item(self, iid, at=None):
        it = self._items.get(iid)
        if it is None:
            it = {"id": iid, "primitives": []}
            self._items[iid] = it
            self.layout["items"].append(it)
        if at is not None:
            it["at"] = r3(at)
        return it

    def capsules(self, iid, phase, polyline, r=COND_R):
        it = self.item(iid)
        pts = [r3(p) for p in polyline]
        for a, b in zip(pts, pts[1:]):
            it["primitives"].append({"type": "capsule", "a": a, "b": b, "r": r, "phase": phase})

    def structure(self, sid, kind, polyline, name=None, r=0.01):
        pts = [r3(p) for p in polyline]
        self.layout["structures"].append({
            "id": sid, "kind": kind, "name": name,
            "primitives": [{"type": "capsule", "a": a, "b": b, "r": r} for a, b in zip(pts, pts[1:])],
        })

    def gantry(self, sid, x0, x1, y, z, name=None, spacing=8.0, beam_z=None):
        """引留鉄構（柱と梁）。柱は spacing ごとに立てる。梁は beam_z（既定は柱の頂部）。"""
        n = max(1, int(round((x1 - x0) / spacing)))
        prims = []
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            prims.append({"type": "capsule", "a": r3((x, y, 0.0)), "b": r3((x, y, z)), "r": GANTRY["col_w"] / 2})
        bz = z if beam_z is None else beam_z
        prims.append({"type": "capsule", "a": r3((x0, y, bz)), "b": r3((x1, y, bz)), "r": GANTRY["beam_h"] / 2})
        self.layout["structures"].append({"id": sid, "kind": "gantry", "name": name, "primitives": prims})

    def apparatus(self, sid, kind, kv, x, y, name=None):
        """避雷器など、結線上は区間の一部で、図面と 3D に形だけ出す機器（3 相）。CT は遮断器に内蔵（ブッシング形）。"""
        e = EQUIP[kv][kind]; sp = EQUIP[kv]["phase_sp"]
        h = e["column"] + e["porcelain"] + e.get("head_h", 0.0)
        prims = [{"type": "capsule", "a": r3((x + PHASE_IDX[ph] * sp, y, 0.0)), "b": r3((x + PHASE_IDX[ph] * sp, y, h)), "r": e.get("head_d", e.get("d", 0.3)) / 2, "phase": ph} for ph in PHASES]
        self.layout["structures"].append({"id": sid, "kind": "instrument" if kind == "ct" else "arrester", "name": name, "primitives": prims})

    def chain(self, refs):
        """端子参照の列を辺でつなぐ（同じ開閉器の a→b は辺にしない）。"""
        for a, b in zip(refs, refs[1:]):
            if a.split(".")[0] == b.split(".")[0]:
                continue
            self.edge(a, b)

    # ======================================================================
    # 220kV 単母線（3 区間）
    # ======================================================================
    def yard_220(self):
        cfg = P["220"]; kv = cfg["kv"]; sp = cfg["phase_sp"]; code = cfg["code"]
        by, bz = cfg["bus"]["y"], cfg["bus"]["z"]
        xs = [cfg["bus"]["x0"]] + [x for _, x in cfg["sections"]] + [cfg["bus"]["x1"]]
        names = ["A", "B", "C"]
        buses = {}
        for i, sec in enumerate(names):
            b = self.node(f"220-BUS-{sec}", "bus", kv, name=f"220kV 母線 {sec}区間")
            buses[sec] = b
            self.es(f"{b}-ES", b, kv, name=f"220kV 母線 {sec}区間 接地", number=f"{code}B-{i + 1}E",
                    at=((xs[i] + xs[i + 1]) / 2, by - 2.0, 1.5))
            for ph in PHASES:
                y = by - PHASE_IDX[ph] * sp
                self.capsules(b, ph, [(xs[i] + (0.0 if i == 0 else 0.6), y, bz), (xs[i + 1] - (0.0 if i == 2 else 0.6), y, bz)], r=BUS_R)
        # セクション LS（母線上。両側の母線区間をつなぐ）
        for i, (sec, x) in enumerate(cfg["sections"]):
            left, right = names[i], names[i + 1]
            s = self.switch(f"220-SEC-{left}{right}", "disconnector", kv, "closed", name=f"220kV セクション断路器 {left}-{right}",
                            at=(x, by, bz), number=f"{code}B-{i + 1}01")
            self.edge(buses[left], f"{s}.a"); self.edge(f"{s}.b", buses[right])
        # 引留鉄構・架空地線
        g = cfg["line_gantry"]
        self.structure("220-GW-N", "ground_wire", [(cfg["bus"]["x0"] - 6, g["y"], cfg["gw_z"]), (cfg["bus"]["x1"] + 6, g["y"], cfg["gw_z"])], name="220kV 架空地線（北）")
        self.gantry("220-GANTRY-LINE", cfg["bus"]["x0"] - 6, cfg["bus"]["x1"] + 6, g["y"], g["column"], "220kV 引留鉄構（北）", beam_z=g["z"])
        for (cid, cname, x, sec) in cfg["lines"]:
            tw = cfg["tower"]
            self.layout["structures"].append({"id": f"220-TOWER-{cid}", "kind": "other", "name": f"{cname} 引留鉄塔（構外）",
                                              "primitives": [{"type": "capsule", "a": r3((x, tw["y"], 0.0)), "b": r3((x, tw["y"], tw["height"])), "r": 1.0}]})
        self.gantry("220-GANTRY-BUS", cfg["bus"]["x0"], cfg["bus"]["x1"], by, bz + 1.5, "220kV 母線鉄構", spacing=23.0)
        # 線路ベイ（母線の北側）
        lb = cfg["line_bay"]
        for i, (cid, cname, x, sec) in enumerate(cfg["lines"]):
            idx = i + 1
            ln = self.node(f"220-LINE-{cid}", "source", kv, name=cname, bay=f"L{idx}")
            self.sources.append(ln)
            pre = f"220-L{idx}"
            ls = self.switch(f"{pre}-LS", "disconnector", kv, "closed", name=f"{cname} 線路断路器", bay=f"L{idx}", at=(x, lb["ls"], cfg["eq_z"]), number=f"{code}{cid}-{idx}100")
            cb = self.switch(f"{pre}-CB", "breaker", kv, "closed", name=f"{cname} 遮断器", bay=f"L{idx}", at=(x, lb["cb"], cfg["eq_z"]), number=f"{code}{cid}-{idx}10")
            bls = self.switch(f"{pre}-BLS", "disconnector", kv, "closed", name=f"{cname} 母線側断路器（パンタ型）", bay=f"L{idx}", at=(x, by, cfg["eq_z"]), number=f"{code}{cid}-{idx}101")
            n1 = self.node(f"{pre}-N1", "terminal", kv, name=f"{cname} 線路側区間", bay=f"L{idx}")
            n2 = self.node(f"{pre}-N2", "terminal", kv, name=f"{cname} 母線側区間", bay=f"L{idx}")
            self.chain([ln, f"{ls}.b", f"{ls}.a", n1, f"{cb}.a", f"{cb}.b", n2, f"{bls}.a", f"{bls}.b", buses[sec]])
            self.es(f"{ln}-ES", ln, kv, name=f"{cname} 線路接地", at=(x - 1.0, lb["ls"] + 2.5, 1.5), number=f"{code}{cid}-{idx}100E")
            self.es(f"{n1}-ES", n1, kv, name=f"{cname} 線路側区間 接地", at=(x + 1.0, (lb["ls"] + lb["cb"]) / 2, 1.5), number=f"{code}{cid}-{idx}101E")
            self.apparatus(f"{pre}-LA", "la", kv, x, lb["la"], f"{cname} 避雷器")
            tw = cfg["tower"]; cz = cfg["cb_z"]
            for ph in PHASES:
                px = x + PHASE_IDX[ph] * sp
                yp = by - PHASE_IDX[ph] * sp       # この相の母線の y ＝ パンタ型断路器の柱の位置
                # 線路: 構外鉄塔 → 引留鉄構の腕 → 垂れ下がって線路断路器へ
                self.capsules(ln, ph, [(px, lb["ls"] + 1.0, cfg["eq_z"]), (px, g["y"], g["z"]), (px, tw["y"], tw["z"])])
                self.capsules(n1, ph, [(px, lb["ls"], cfg["eq_z"]), (px, lb["cb"] + EQUIP[220]["cb"]["bushing_pitch"] / 2, cz)])
                self.capsules(n2, ph, [(px, lb["cb"] - EQUIP[220]["cb"]["bushing_pitch"] / 2, cz), (px, yp + 0.6, cfg["eq_z"])])
                # パンタ型断路器の柱頭 → 母線（真上）。母線区間の導体として持つ
                self.capsules(buses[sec], ph, [(px, yp, cfg["eq_z"]), (px, yp, bz)])
        # 変圧器ベイ（母線の南側）
        tb = cfg["tr_bay"]
        for (n, x, sec) in cfg["banks"]:
            pre = f"220-T{n}"
            bls = self.switch(f"{pre}-BLS", "disconnector", kv, "closed", name=f"{n}号変圧器 一次 母線側断路器（パンタ型）", bay=f"T{n}", at=(x, by, cfg["eq_z"]), number=f"{code}T-{n}101")
            cb = self.switch(f"{pre}-CB", "breaker", kv, "closed", name=f"{n}号変圧器 一次 遮断器", bay=f"T{n}", at=(x, tb["cb"], cfg["eq_z"]), number=f"{code}T-{n}10")
            ls = self.switch(f"{pre}-LS", "disconnector", kv, "closed", name=f"{n}号変圧器 一次 機器側断路器", bay=f"T{n}", at=(x, tb["ls"], cfg["eq_z"]), number=f"{code}T-{n}100")
            n1 = self.node(f"{pre}-N1", "terminal", kv, name=f"{n}号変圧器 一次 母線側区間", bay=f"T{n}")
            n2 = self.node(f"{pre}-N2", "terminal", kv, name=f"{n}号変圧器 一次 遮断器-断路器間", bay=f"T{n}")
            hv = self.node(f"220-TR-{n}-HV", "terminal", kv, name=f"{n}号変圧器 一次", bay=f"T{n}")
            self.chain([buses[sec], f"{bls}.a", f"{bls}.b", n1, f"{cb}.a", f"{cb}.b", n2, f"{ls}.a", f"{ls}.b", hv])
            self.es(f"{n2}-ES", n2, kv, name=f"{n}号変圧器 一次 遮断器-断路器間 接地", at=(x + 1.0, (tb["cb"] + tb["ls"]) / 2, 1.5), number=f"{code}T-{n}101E")
            self.es(f"{hv}-ES", hv, kv, name=f"{n}号変圧器 一次 接地", at=(x - 1.0, tb["ls"] - 2.5, 1.5), number=f"{code}T-{n}100E")
            self.apparatus(f"{pre}-LA", "la", kv, x, tb["la"], f"{n}号変圧器 一次 避雷器")
            cz = cfg["cb_z"]
            for ph in PHASES:
                px = x + PHASE_IDX[ph] * sp
                yp = by - PHASE_IDX[ph] * sp
                self.capsules(buses[sec], ph, [(px, yp, bz), (px, yp, cfg["eq_z"])])
                self.capsules(n1, ph, [(px, yp - 0.6, cfg["eq_z"]), (px, tb["cb"] + EQUIP[220]["cb"]["bushing_pitch"] / 2, cz)])
                self.capsules(n2, ph, [(px, tb["cb"] - EQUIP[220]["cb"]["bushing_pitch"] / 2, cz), (px, tb["ls"], cfg["eq_z"])])
                bx = x + PHASE_IDX[ph] * TRANSFORMER["hv_pitch"]
                self.capsules(hv, ph, [(px, tb["ls"], cfg["eq_z"]), (px, tb["la"], cfg["eq_z"]), (bx, cfg["tr_y"] + TRANSFORMER["hv"]["y"], cfg["tr_z"])])
            d = self._tr.setdefault(n, {})
            d["hv"] = hv
            d["at"] = (x, cfg["tr_y"], 0.0)

    # ======================================================================
    # 66kV 1・1/2 母線
    # ======================================================================
    def diameter_66(self, bay, x_bay, c1, c2, cfg, bus_a, bus_b, idx):
        kv, sp, eqz = cfg["kv"], cfg["phase_sp"], cfg["eq_z"]
        yA, yB = cfg["busA"]["y"], cfg["busB"]["y"]
        margin = sp + 1.0
        pitch = (abs(yA - yB) - 2 * margin) / 8.0
        ys = [yA - margin - i * pitch for i in range(9)]
        (y_LSA, y_CB1, y_LS1B, y_LS2A, y_CB2, y_LS2B, y_LS3A, y_CB3, y_LSB) = ys
        pre = f"66-{bay}"
        new_bay = (c1 is None and c2 is None)
        nrm = "open" if new_bay else "closed"
        code = cfg["code"]

        def sysc(c):
            if c is None:
                return "X"
            return {"line": lambda: c[1], "tr": lambda: "T", "load": lambda: c[1][:2]}[c[0]]()
        sys1, sys2 = sysc(c1), sysc(c2)
        num = {
            "CB1": f"{code}{sys1}-{idx}10", "LSA": f"{code}{sys1}-{idx}101", "LS1B": f"{code}{sys1}-{idx}103",
            "CB2": f"{code}M-{idx}20", "LS2A": f"{code}M-{idx}201", "LS2B": f"{code}M-{idx}203",
            "CB3": f"{code}{sys2}-{idx}30", "LS3A": f"{code}{sys2}-{idx}303", "LSB": f"{code}{sys2}-{idx}301",
        }

        def pos(y):
            return (x_bay, y, eqz)

        names = {"T1": f"{bay} 北側回路引出点", "T2": f"{bay} 南側回路引出点"}
        N = {k: self.node(f"{pre}-{k}", "terminal", kv, name=names.get(k), bay=bay)
             for k in ("N1", "N2", "T1", "N3", "N4", "T2", "N5", "N6")}
        S = {}
        for sid, kind, y in (("LSA", "disconnector", y_LSA), ("CB1", "breaker", y_CB1), ("LS1B", "disconnector", y_LS1B),
                             ("LS2A", "disconnector", y_LS2A), ("CB2", "breaker", y_CB2), ("LS2B", "disconnector", y_LS2B),
                             ("LS3A", "disconnector", y_LS3A), ("CB3", "breaker", y_CB3), ("LSB", "disconnector", y_LSB)):
            S[sid] = self.switch(f"{pre}-{sid}", kind, kv, nrm, bay=bay, at=pos(y), number=num[sid])

        drop_a = self.edge(bus_a, f"{S['LSA']}.a", eid=f"{pre}-DROP-A")
        drop_b = self.edge(bus_b, f"{S['LSB']}.b", eid=f"{pre}-DROP-B")
        chain = [(S["LSA"], "b"), N["N1"], (S["CB1"], "a"), (S["CB1"], "b"), N["N2"], (S["LS1B"], "a"), (S["LS1B"], "b"),
                 N["T1"], (S["LS2A"], "a"), (S["LS2A"], "b"), N["N3"], (S["CB2"], "a"), (S["CB2"], "b"), N["N4"],
                 (S["LS2B"], "a"), (S["LS2B"], "b"), N["T2"], (S["LS3A"], "a"), (S["LS3A"], "b"), N["N5"],
                 (S["CB3"], "a"), (S["CB3"], "b"), N["N6"], (S["LSB"], "a")]
        self.chain([(f"{x[0]}.{x[1]}" if isinstance(x, tuple) else x) for x in chain])

        segs = {"N1": (y_LSA, y_CB1), "N2": (y_CB1, y_LS1B), "T1": (y_LS1B, y_LS2A), "N3": (y_LS2A, y_CB2),
                "N4": (y_CB2, y_LS2B), "T2": (y_LS2B, y_LS3A), "N5": (y_LS3A, y_CB3), "N6": (y_CB3, y_LSB)}
        es_num = {"N1": num["LSA"], "N2": num["LS1B"], "T1": num["LS1B"], "N3": num["LS2A"],
                  "N4": num["LS2B"], "T2": num["LS3A"], "N5": num["LS3A"], "N6": num["LSB"]}
        for k, (y0, y1) in segs.items():
            self.es(f"{N[k]}-ES", N[k], kv, at=(x_bay + 1.0, (y0 + y1) / 2, 1.5), number=es_num[k] + "E")

        if new_bay:
            return

        for ph in PHASES:
            x = x_bay + PHASE_IDX[ph] * sp
            ya = yA - PHASE_IDX[ph] * sp
            yb = yB - PHASE_IDX[ph] * sp
            self.capsules(drop_a, ph, [(x, ya, cfg["busA"]["z"]), (x, ya, eqz), (x, y_LSA, eqz)])
            self.capsules(drop_b, ph, [(x, yb, cfg["busB"]["z"]), (x, yb, eqz), (x, y_LSB, eqz)])
            for k, (y0, y1) in segs.items():
                self.capsules(N[k], ph, [(x, y0, eqz), (x, y1, eqz)])

        self._circuit_66(bay, x_bay, c1, N["T1"], (y_LS1B + y_LS2A) / 2, "N", cfg, f"{code}{sys1}-{idx}100")
        self._circuit_66(bay, x_bay, c2, N["T2"], (y_LS2B + y_LS3A) / 2, "S", cfg, f"{code}{sys2}-{idx}300")

    def _circuit_66(self, bay, x_bay, c, tap, y_tap, side, cfg, number):
        kind, cid, cname = c
        kv, sp, eqz = cfg["kv"], cfg["phase_sp"], cfg["eq_z"]
        ng, lg = cfg["north_gantry"], cfg["line_gantry"]
        if kind == "line":
            ln = f"66-LINE-{cid}"
            self.node(ln, "source", kv, name=cname, bay=bay)
            self.sources.append(ln)
            ls = self.switch(f"{ln}-LS", "disconnector", kv, "closed", name=f"{cname} 線路断路器", bay=bay, at=(x_bay, y_tap, eqz), number=number)
            self.edge(tap, f"{ls}.a"); self.edge(f"{ls}.b", ln)
            self.es(f"{ln}-ES", ln, kv, name=f"{cname} 線路接地", at=(x_bay - 1.0, y_tap, 1.5), number=number + "E")
            self.apparatus(f"{ln}-LA", "la", kv, x_bay, lg["y"] + 3.0, f"{cname} 避雷器")
            for ph in PHASES:
                x = x_bay + PHASE_IDX[ph] * sp
                # 線路は南側回路。南の引留鉄構へ
                self.capsules(ln, ph, [(x, y_tap, eqz), (x, y_tap, lg["z"] - 3.0), (x, lg["y"], lg["z"])])
        elif kind == "tr":
            term = self.node(f"66-TR-{cid}-LV", "terminal", kv, name=cname, bay=bay)
            ls = self.switch(f"66-TR-{cid}-LS", "disconnector", kv, "closed", name=f"{cname} 断路器", bay=bay, at=(x_bay, y_tap, eqz), number=number)
            self.edge(tap, f"{ls}.a"); self.edge(f"{ls}.b", term)
            self.es(f"66-TR-{cid}-ES", term, kv, name=f"{cname} 接地", at=(x_bay - 1.0, y_tap, 1.5), number=number + "E")
            x_tr = next(x for (n, x, _) in P["220"]["banks"] if n == cid)
            y_tr = P["220"]["tr_y"] + TRANSFORMER["lv"]["y"]   # 二次ブッシングは変圧器の南側
            for ph in PHASES:
                x = x_bay + PHASE_IDX[ph] * sp
                xt = x_tr + PHASE_IDX[ph] * sp
                xb = x_tr + PHASE_IDX[ph] * TRANSFORMER["lv_pitch"]
                # 北の引留鉄構へ上げ、引留上の渡り線で変圧器の真南へ、二次ブッシングへ降りる
                pts = [(x, y_tap, eqz), (x, y_tap, ng["z"] - 3.0), (x, ng["y"], ng["z"]), (xt, ng["y"] + 1.0, ng["z"]), (xb, y_tr, cfg["tr_lv_z"])]
                self.capsules(term, ph, pts)
            d = self._tr.setdefault(cid, {})
            d["lv"] = term
        elif kind == "load":
            lid = f"66-{cid[:2]}-{cid[2:]}"
            self.node(lid, "load", kv, name=cname, bay=bay)
            ls = self.switch(f"{lid}-LS", "disconnector", kv, "closed", name=f"{cname} 断路器", bay=bay, at=(x_bay, y_tap, eqz), number=number)
            self.edge(tap, f"{ls}.a"); self.edge(f"{ls}.b", lid)
            self.es(f"{lid}-ES", lid, kv, name=f"{cname} 接地", at=(x_bay - 1.0, y_tap, 1.5), number=number + "E")
            self.item(lid, at=(x_bay, cfg["load_y"], 0.0))
            for ph in PHASES:
                x = x_bay + PHASE_IDX[ph] * sp
                self.capsules(lid, ph, [(x, y_tap, eqz), (x, y_tap, ng["z"] - 3.0), (x, ng["y"], ng["z"]), (x, cfg["load_y"], eqz)])

    def yard_66(self):
        cfg = P["66"]; kv = cfg["kv"]
        bus_a = self.node("66-BUS-A", "bus", kv, name="66kV 1号母線")
        bus_b = self.node("66-BUS-B", "bus", kv, name="66kV 2号母線")
        self.es(f"{bus_a}-ES", bus_a, kv, name="66kV 1号母線接地", number=f"{cfg['code']}A-10E")
        self.es(f"{bus_b}-ES", bus_b, kv, name="66kV 2号母線接地", number=f"{cfg['code']}B-10E")
        n_bays = len(cfg["bays"])
        x_min = cfg["x0"] - cfg["bay_pitch"] / 2.0
        x_max = cfg["x0"] + cfg["bay_pitch"] * (n_bays - 0.5)
        sp = cfg["phase_sp"]
        for ph in PHASES:
            for bus, b in (("A", bus_a), ("B", bus_b)):
                y = cfg[f"bus{bus}"]["y"] - PHASE_IDX[ph] * sp
                z = cfg[f"bus{bus}"]["z"]
                self.capsules(b, ph, [(x_min, y, z), (x_max, y, z)], r=BUS_R)
        for i, (bay, c1, c2) in enumerate(cfg["bays"]):
            self.diameter_66(bay, cfg["x0"] + i * cfg["bay_pitch"], c1, c2, cfg, bus_a, bus_b, idx=i + 1)
        self.structure("66-GW-S", "ground_wire", [(x_min - 5.0, cfg["line_gantry"]["y"], cfg["gw_z"]), (x_max + 5.0, cfg["line_gantry"]["y"], cfg["gw_z"])], name="66kV 架空地線（南）")
        self.gantry("66-GANTRY-LINE", x_min - 4.0, x_max + 4.0, cfg["line_gantry"]["y"], cfg["line_gantry"]["z"], "66kV 引留鉄構（南）")
        self.gantry("66-GANTRY-N", x_min - 4.0, x_max + 4.0, cfg["north_gantry"]["y"], cfg["north_gantry"]["z"], "66kV 引留鉄構（北・変圧器二次/調相）")
        self.gantry("66-GANTRY-BUS-A", x_min, x_max, cfg["busA"]["y"], cfg["busA"]["z"] + 1.5, "66kV 1号母線鉄構", spacing=14.0)
        self.gantry("66-GANTRY-BUS-B", x_min, x_max, cfg["busB"]["y"], cfg["busB"]["z"] + 1.5, "66kV 2号母線鉄構", spacing=14.0)

    def transformers(self):
        for n, d in sorted(self._tr.items()):
            tid = f"TR-{n}"
            self.node(tid, "transformer", name=f"{n}号変圧器 220/66kV", number=f"{n}BK",
                      windings={"hv": {"voltage_kv": P["220"]["kv"]}, "lv": {"voltage_kv": P["66"]["kv"]}})
            self.edge(d["hv"], f"{tid}.hv", conductor="enclosed")
            self.edge(d["lv"], f"{tid}.lv", conductor="enclosed")
            self.item(tid, at=d["at"])

    # ---- 状態ファイル ----
    def state(self, step: int, note: str, switches: dict | None = None, sources: dict | None = None) -> dict:
        sw = dict(self.normal_switches)
        sw.update(switches or {})
        src = {s: "live" for s in self.sources}
        src.update(sources or {})
        return {"schema_version": "0.1", "site_id": SITE_ID, "step": step, "note": note, "sources": src, "switches": sw}


def build() -> Site:
    s = Site(P["name"])
    s.yard_220()
    s.yard_66()
    s.transformers()
    return s


def example_states(s: Site) -> dict[str, dict]:
    """§15 の手元確認と、テストで使う停止例。"""
    tr2_220_only = {
        "220-T2-CB": "open", "220-T2-BLS": "open", "220-T2-LS": "open",
        "220-TR-2-HV-ES": "closed",
    }
    tr2_both = dict(tr2_220_only, **{"66-TR-2-LS": "open"})
    sec_b = {
        # 中央セクション B の停止: 両側のセクション LS を開き、2号変圧器を母線から切り離し、母線に接地。
        # A・C 区間は線路と変圧器で運転継続
        "220-SEC-AB": "open", "220-SEC-BC": "open", "220-T2-BLS": "open", "220-T2-CB": "open", "220-T2-LS": "open",
        "220-BUS-B-ES": "closed", "66-TR-2-LS": "open",
    }
    return {
        "normal": s.state(0, "通常（66kV D6 は新設予定で未接続）"),
        "tr2-outage-220-only": s.state(1, "2号変圧器の 220kV 側だけを切って一次に接地（66kV 側からの逆送で invalid になる例）", tr2_220_only),
        "tr2-outage": s.state(2, "2号変圧器を両側で切り離して一次に接地（母線と他バンク・線路は運転継続）", tr2_both),
        "sec-b-outage": s.state(3, "220kV 母線 中央セクション B を停止して接地（A・C 区間は線路と変圧器で運転継続）", sec_b),
    }


def main():
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else \
        pathlib.Path(__file__).resolve().parent.parent / "data" / "sites" / SITE_ID / "truth"
    out.mkdir(parents=True, exist_ok=True)
    (out / "states").mkdir(exist_ok=True)
    s = build()
    (out / "topology.json").write_text(json.dumps(s.topo, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "layout.json").write_text(json.dumps(s.layout, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, st in example_states(s).items():
        (out / "states" / f"{name}.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}: nodes={len(s.topo['nodes'])} edges={len(s.topo['edges'])} items={len(s.layout['items'])}")


if __name__ == "__main__":
    main()
