#!/usr/bin/env python3
"""合成変電所 SITE-01（220/66kV・1・1/2 母線・変圧器 2 台）の生成。

全ての寸法は仮定値。社内標準・実在設備の値ではない。パラメータ P を変えて再生成すれば別の構内になる。

出力（契約の形）:
  data/sites/SITE-01/truth/topology.json   §6.1 図面の構造
  data/sites/SITE-01/truth/layout.json     §6.2 配置（カプセル）
  data/sites/SITE-01/truth/states/*.json   §6.3 開閉器の状態（通常／停止例）

使い方:
  python -m synth.gen_site                 # data/sites/SITE-01 に出力
  python -m synth.gen_site path/to/dir

命名の約束（IDは英数字と - のみ）:
  <kV>-BUS-A / -B            母線（bus）
  <kV>-D<n>-LSA … -LSB       ダイヤの開閉器（disconnector / breaker）
  <kV>-D<n>-N1 … -N6, -T1/-T2  開閉器間の区間と引出点（terminal）
  <kV>-LINE-<方面><n>         線路（source）。方面は E/W/N/S/P の符号、名前は「東線1L」など
  TR-<n>                      変圧器（transformer）。端子は TR-n.hv / TR-n.lv
  <kV>-TR-<n>-HV / -LV        変圧器ブッシング側の区間（terminal）
  *-ES                        接地開閉器（earthing）。attached_to に接地する区間
"""
from __future__ import annotations

import json
import pathlib
import sys

SITE_ID = "SITE-01"
GENERATED_BY = "synth/gen_site.py"

# --------------------------------------------------------------------------
# パラメータ（仮定値）
# --------------------------------------------------------------------------
P = {
    "name": "合成変電所 SITE-01（220/66kV, 1・1/2母線, 変圧器2台）",
    "220": {
        "kv": 220,
        "bay_pitch": 18.0,          # ダイヤ（ベイ）間隔
        "phase_sp": 4.0,            # 相間隔
        "busA": {"y": 0.0, "z": 10.5},    # A母線（上段）
        "busB": {"y": -36.0, "z": 6.5},   # B母線（下段）
        "eq_z": 5.0,                # 機器端子高さ
        "gw_z": 25.0,               # 架空地線 引止め高さ（雷遮蔽設計で決まる。仮定）
        "gw_y": (8.0, -44.0),
        "line_z": 20.0,             # 引込線の引止め高さ
        "line_y": (8.0, -44.0),
        "tr_dx": 9.0,               # 変圧器端子の x オフセット
        "tr_z": 3.0,                # 変圧器ブッシング端子高さ
        "x0": 0.0,
        "bays": [
            # (ベイID, 北側回路, 南側回路)。回路は ("line", 符号, 名前) か ("tr", 番号, 名前)
            ("D1", ("line", "E1", "東線1L"), ("tr", 1, "1号変圧器 一次")),
            ("D2", ("line", "E2", "東線2L"), ("tr", 2, "2号変圧器 一次")),
            ("D3", ("line", "W1", "西線1L"), ("line", "W2", "西線2L")),
            ("D4", None, None),  # 新設 GIS ベイ（母線は延長済み、機器未接続）
        ],
    },
    "66": {
        "kv": 66,
        "bay_pitch": 10.0,
        "phase_sp": 2.0,
        "busA": {"y": -80.0, "z": 6.5},
        "busB": {"y": -104.0, "z": 4.5},
        "eq_z": 3.0,
        "gw_z": 14.0,
        "gw_y": (-72.0, -112.0),
        "line_z": 10.0,
        "line_y": (-72.0, -112.0),
        "tr_dx": 5.0,
        "tr_z": 2.0,
        "x0": 0.0,
        "bays": [
            ("D1", ("line", "N1", "北線1L"), ("tr", 1, "1号変圧器 二次")),
            ("D2", ("line", "N2", "北線2L"), ("tr", 2, "2号変圧器 二次")),
            ("D3", ("line", "S1", "南線1L"), ("line", "S2", "南線2L")),
            ("D4", ("line", "P1", "港線1L"), ("line", "P2", "港線2L")),
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
            "notes": ["合成データ。実在の設備・事業者・図面とは無関係。", "寸法・構成はすべて仮定値。"],
            "nodes": [], "edges": [], "questions": [],
        }
        self.layout = {
            "schema_version": "0.1", "site_id": SITE_ID, "generated_by": GENERATED_BY,
            "origin_note": "基準点 P1 = 220kV 構内 D1 ダイヤ中心の直下, X=東, Y=北, Z=上（仮定）",
            "notes": ["全寸法は仮定値。架空地線の高さは雷遮蔽設計で決まるため、ここでは仮定。"],
            "reference_points": [{"id": "P1", "x": 0.0, "y": 0.0, "z": 0.0}, {"id": "P2", "x": 40.0, "y": 0.0, "z": 0.0}],
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
        d.update(extra)
        self.topo["nodes"].append(d)
        return nid

    def switch(self, sid, kind, kv, normal, name=None, bay=None, at=None):
        self.node(sid, kind, kv, name, bay)
        self.normal_switches[sid] = normal
        if at is not None:
            self.item(sid, at=at)
        return sid

    def es(self, eid, attached_to, kv, name=None, at=None):
        self.node(eid, "earthing", kv, name, attached_to=attached_to)
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

    # ---- 1・1/2 母線のダイヤ（ベイ）を1つ生成 ----
    def diameter(self, vl, bay, x_bay, c1, c2, cfg, bus_a, bus_b):
        kv, sp, eqz = cfg["kv"], cfg["phase_sp"], cfg["eq_z"]
        yA, yB = cfg["busA"]["y"], cfg["busB"]["y"]
        margin = sp + 2.0
        pitch = (abs(yA - yB) - 2 * margin) / 8.0
        ys = [yA - margin - i * pitch for i in range(9)]
        (y_LSA, y_CB1, y_LS1B, y_LS2A, y_CB2, y_LS2B, y_LS3A, y_CB3, y_LSB) = ys
        pre = f"{vl}-{bay}"
        new_bay = (c1 is None and c2 is None)
        nrm = "open" if new_bay else "closed"

        def pos(y):
            return (x_bay, y, eqz)

        # 区間（terminal）と開閉器
        names = {"T1": f"{bay} 北側回路引出点", "T2": f"{bay} 南側回路引出点"}
        N = {k: self.node(f"{pre}-{k}", "terminal", kv, name=names.get(k), bay=bay)
             for k in ("N1", "N2", "T1", "N3", "N4", "T2", "N5", "N6")}
        S = {}
        for sid, kind, y in (("LSA", "disconnector", y_LSA), ("CB1", "breaker", y_CB1), ("LS1B", "disconnector", y_LS1B),
                             ("LS2A", "disconnector", y_LS2A), ("CB2", "breaker", y_CB2), ("LS2B", "disconnector", y_LS2B),
                             ("LS3A", "disconnector", y_LS3A), ("CB3", "breaker", y_CB3), ("LSB", "disconnector", y_LSB)):
            S[sid] = self.switch(f"{pre}-{sid}", kind, kv, nrm, bay=bay, at=pos(y))

        # 母線 → ドロッパー（辺にカプセル） → LSA.a
        drop_a = self.edge(bus_a, f"{S['LSA']}.a", eid=f"{pre}-DROP-A")
        drop_b = self.edge(bus_b, f"{S['LSB']}.b", eid=f"{pre}-DROP-B")
        # 開閉器 ⇄ 区間（長さゼロの辺。導体は区間ノードのカプセル）
        chain = [(S["LSA"], "b"), N["N1"], (S["CB1"], "a"), (S["CB1"], "b"), N["N2"], (S["LS1B"], "a"), (S["LS1B"], "b"),
                 N["T1"], (S["LS2A"], "a"), (S["LS2A"], "b"), N["N3"], (S["CB2"], "a"), (S["CB2"], "b"), N["N4"],
                 (S["LS2B"], "a"), (S["LS2B"], "b"), N["T2"], (S["LS3A"], "a"), (S["LS3A"], "b"), N["N5"],
                 (S["CB3"], "a"), (S["CB3"], "b"), N["N6"], (S["LSB"], "a")]
        refs = [(f"{x[0]}.{x[1]}" if isinstance(x, tuple) else x) for x in chain]
        for a, b in zip(refs, refs[1:]):
            if a.split(".")[0] == b.split(".")[0]:
                continue  # 同じ開閉器の a→b は辺ではない
            self.edge(a, b)

        # 接地開閉器（引出点と、遮断器両側の区間。点検用）
        segs = {"N1": (y_LSA, y_CB1), "N2": (y_CB1, y_LS1B), "T1": (y_LS1B, y_LS2A), "N3": (y_LS2A, y_CB2),
                "N4": (y_CB2, y_LS2B), "T2": (y_LS2B, y_LS3A), "N5": (y_LS3A, y_CB3), "N6": (y_CB3, y_LSB)}
        for k, (y0, y1) in segs.items():
            self.es(f"{N[k]}-ES", N[k], kv, at=(x_bay + 1.0, (y0 + y1) / 2, 1.5))

        if new_bay:
            return  # 新設ベイ: 母線は延長済み、機器導体は未設置

        # 導体カプセル
        for ph in PHASES:
            x = x_bay + PHASE_IDX[ph] * sp
            ya = yA - PHASE_IDX[ph] * sp
            yb = yB - PHASE_IDX[ph] * sp
            self.capsules(drop_a, ph, [(x, ya, cfg["busA"]["z"]), (x, ya, eqz), (x, y_LSA, eqz)])
            self.capsules(drop_b, ph, [(x, yb, cfg["busB"]["z"]), (x, yb, eqz), (x, y_LSB, eqz)])
            for k, (y0, y1) in segs.items():
                self.capsules(N[k], ph, [(x, y0, eqz), (x, y1, eqz)])

        self._circuit(vl, bay, x_bay, c1, N["T1"], (y_LS1B + y_LS2A) / 2, "N", cfg)
        self._circuit(vl, bay, x_bay, c2, N["T2"], (y_LS2B + y_LS3A) / 2, "S", cfg)

    def _circuit(self, vl, bay, x_bay, c, tap, y_tap, side, cfg):
        kind, cid, cname = c
        kv, sp, eqz = cfg["kv"], cfg["phase_sp"], cfg["eq_z"]
        if kind == "line":
            ln = f"{vl}-LINE-{cid}"
            self.node(ln, "source", kv, name=cname, bay=bay)
            self.sources.append(ln)
            ls = self.switch(f"{ln}-LS", "disconnector", kv, "closed", name=f"{cname} 線路断路器", bay=bay, at=(x_bay, y_tap, eqz))
            self.edge(tap, f"{ls}.a")
            self.edge(f"{ls}.b", ln)
            self.es(f"{ln}-ES", ln, kv, name=f"{cname} 線路接地", at=(x_bay - 1.0, y_tap, 1.5))
            y_end = cfg["line_y"][0] if side == "N" else cfg["line_y"][1]
            for ph in PHASES:
                x = x_bay + PHASE_IDX[ph] * sp
                self.capsules(ln, ph, [(x, y_tap, eqz), (x, y_tap, cfg["line_z"] - 4.0), (x, y_end, cfg["line_z"])])
        elif kind == "tr":
            side_name = "HV" if vl == "220" else "LV"
            term = self.node(f"{vl}-TR-{cid}-{side_name}", "terminal", kv, name=cname, bay=bay)
            ls = self.switch(f"{vl}-TR-{cid}-LS", "disconnector", kv, "closed", name=f"{cname} 断路器", bay=bay, at=(x_bay + 2.0, y_tap, eqz))
            self.edge(tap, f"{ls}.a")
            self.edge(f"{ls}.b", term)
            self.es(f"{vl}-TR-{cid}-ES", term, kv, name=f"{cname} 接地", at=(x_bay + 3.0, y_tap, 1.5))
            for ph in PHASES:
                x = x_bay + PHASE_IDX[ph] * sp
                self.capsules(term, ph, [(x, y_tap, eqz), (x + cfg["tr_dx"], y_tap, eqz), (x + cfg["tr_dx"], y_tap, cfg["tr_z"])])
            d = self._tr.setdefault(cid, {})
            d[side_name.lower()] = term
            d.setdefault("at", (x_bay + cfg["tr_dx"], y_tap, 0.0))

    # ---- 構内（電圧階級）を1つ生成 ----
    def yard(self, vl):
        cfg = P[vl]
        kv = cfg["kv"]
        bus_a = self.node(f"{vl}-BUS-A", "bus", kv, name=f"{vl}kV A母線")
        bus_b = self.node(f"{vl}-BUS-B", "bus", kv, name=f"{vl}kV B母線")
        self.es(f"{bus_a}-ES", bus_a, kv, name=f"{vl}kV A母線接地")
        self.es(f"{bus_b}-ES", bus_b, kv, name=f"{vl}kV B母線接地")

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
            self.diameter(vl, bay, cfg["x0"] + i * cfg["bay_pitch"], c1, c2, cfg, bus_a, bus_b)

        for i, y in enumerate(cfg["gw_y"]):
            tag = "N" if i == 0 else "S"
            self.structure(f"{vl}-GW-{tag}", "ground_wire",
                           [(x_min - 5.0, y, cfg["gw_z"]), (x_max + 5.0, y, cfg["gw_z"])],
                           name=f"{vl}kV 架空地線（{'北' if tag == 'N' else '南'}）")

    def transformers(self):
        for n, d in sorted(self._tr.items()):
            tid = f"TR-{n}"
            self.node(tid, "transformer", name=f"{n}号変圧器 220/66kV",
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
    s.yard("220")
    s.yard("66")
    s.transformers()
    return s


def example_states(s: Site) -> dict[str, dict]:
    """§15 の手元確認と、テストで使う停止例。"""
    tr2_220_only = {
        "220-D2-CB2": "open", "220-D2-LS2B": "open", "220-D2-CB3": "open", "220-D2-LS3A": "open",
        "220-D2-T2-ES": "closed",
    }
    tr2_both = dict(tr2_220_only, **{"66-TR-2-LS": "open"})
    return {
        "normal": s.state(0, "通常（新設ベイ D4 は未接続）"),
        "tr2-outage-220-only": s.state(1, "2号変圧器の 220kV 側だけを切って引出点に接地（66kV 側からの逆送で invalid になる例）", tr2_220_only),
        "tr2-outage": s.state(2, "2号変圧器を両側で切り離して引出点に接地（東線2L は CB1 経由で運転継続）", tr2_both),
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
