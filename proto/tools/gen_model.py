#!/usr/bin/env python3
"""
架空変電所モデル生成スクリプト（MAAI）

全ての寸法は「架空変電所の仮定値」。社内標準・実在設備の値ではない。
パラメータ P を変えて再生成すれば、別の構内モデルになる。

使い方:
    python3 tools/gen_model.py                  # data/substation_fictional.json を出力
    python3 tools/gen_model.py path/to/out.json
"""
import json
import sys
import pathlib

# --------------------------------------------------------------------------
# パラメータ（仮定値）
# --------------------------------------------------------------------------
P = {
    "name": "架空変電所（220/66kV, 1・1/2母線）",
    # 220kV 構内
    "220": {
        "bay_pitch": 18.0,          # ダイヤ（ベイ）間隔
        "phase_sp": 4.0,            # 相間隔
        "busA": {"y": 0.0, "z": 10.5},    # A母線（上段）
        "busB": {"y": -36.0, "z": 6.5},   # B母線（下段）
        "eq_z": 5.0,                # 機器端子高さ
        "gw_z": 25.0,               # 架空地線 引止め高さ（雷遮蔽設計で決まる。仮定）
        "gw_y": (8.0, -44.0),       # 架空地線の位置（北・南）
        "line_z": 20.0,             # 引込線の引止め高さ
        "line_y": (8.0, -44.0),     # 引込線引止め（北・南）
        "tr_dx": 9.0,               # 変圧器端子の x オフセット
        "tr_z": 3.0,                # 変圧器ブッシング端子高さ
        "x0": 0.0,
        "bays": [
            # (ベイID, 北側回路(T1), 南側回路(T2))
            ("D1", ("line", "OPUS1L", "Opus線1L"), ("tr", "TR1", "1号変圧器 一次")),
            ("D2", ("line", "FABLE1L", "Fable線1L"), ("tr", "TR2", "2号変圧器 一次")),
            ("D3", ("line", "OPUS2L", "Opus線2L"), ("line", "FABLE2L", "Fable線2L")),
            ("D4", None, None),  # 新設 GIS ベイ（今回の題材。母線は延長済み、機器未接続）
        ],
    },
    # 66kV 構内
    "66": {
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
            ("D1", ("line", "SONNET1L", "Sonnet線1L"), ("tr", "TR1", "1号変圧器 二次")),
            ("D2", ("line", "HAIKU1L", "Haiku線1L"), ("tr", "TR2", "2号変圧器 二次")),
            ("D3", ("line", "SONNET2L", "Sonnet線2L"), ("line", "HAIKU2L", "Haiku線2L")),
            ("D4", ("line", "MYTHOS1L", "Mythos線1L"), ("line", "MYTHOS2L", "Mythos線2L")),
        ],
    },
    "voltage_levels": [
        {
            "id": "220", "nominal_kv": 220,
            "approach_limit_m": None,        # 法令値はユーザーが出典付きで入れる
            "working_clearance_m": None,     # 運用上の安全離隔もユーザーが入れる
            "phase_to_ground_clearance_m": 2.6,
            "source": "TODO: 公開資料の出典を記入",
        },
        {
            "id": "66", "nominal_kv": 66,
            "approach_limit_m": None,
            "working_clearance_m": None,
            "phase_to_ground_clearance_m": 1.0,
            "source": "TODO: 公開資料の出典を記入",
        },
    ],
}

PHASES = ["R", "S", "T"]
PHASE_IDX = {"R": -1, "S": 0, "T": 1}


def r3(p):
    return [round(float(v), 3) for v in p]


class Model:
    def __init__(self, name):
        self.m = {
            "meta": {
                "name": name,
                "fictional": True,
                "schema_version": "0.1.0",
                "coordinate_system": {"unit": "m", "x": "east", "y": "north", "z": "up"},
                "notes": [
                    "全寸法は架空変電所の仮定値。社内標準・実在設備の値ではない。",
                    "架空地線の高さは雷遮蔽設計で決まるため一概には言えない。ここでは仮定値。",
                    "変圧器まわりの導体経路は簡略化（TODO）。",
                    "生成元: tools/gen_model.py",
                ],
            },
            "voltage_levels": P["voltage_levels"],
            "nodes": [], "switches": [], "earth_switches": [], "sources": [],
            "transformers": [], "conductors": [], "structures": [],
        }
        self._tr = {}  # TR id -> {"hv": node, "lv": node}

    # ---- 基本要素 ----
    def node(self, nid, vl, kind, name=None, bay=None):
        d = {"id": nid, "voltage": vl, "kind": kind}
        if name: d["name"] = name
        if bay: d["bay"] = bay
        self.m["nodes"].append(d)
        return nid

    def switch(self, sid, kind, a, b, normal, name=None, bay=None, pos=None, subtype=None):
        d = {"id": sid, "kind": kind, "from": a, "to": b, "normal": normal}
        if subtype: d["subtype"] = subtype
        if name: d["name"] = name
        if bay: d["bay"] = bay
        if pos is not None: d["position"] = r3(pos)
        self.m["switches"].append(d)

    def es(self, eid, node, name=None, pos=None):
        d = {"id": eid, "node": node, "normal": "open"}
        if name: d["name"] = name
        if pos is not None: d["position"] = r3(pos)
        self.m["earth_switches"].append(d)

    def source(self, sid, node, name):
        self.m["sources"].append({"id": sid, "node": node, "in_service": True, "name": name})

    def conductor(self, cid, node, phase, ctype, polyline, radius=0.02):
        self.m["conductors"].append({
            "id": cid, "node": node, "phase": phase, "type": ctype,
            "radius_m": radius, "polyline": [r3(p) for p in polyline],
        })

    def structure(self, sid, stype, polyline, name=None, radius=None):
        d = {"id": sid, "type": stype, "polyline": [r3(p) for p in polyline]}
        if name: d["name"] = name
        if radius: d["radius_m"] = radius
        self.m["structures"].append(d)

    # ---- 1・1/2 母線のダイヤ（ベイ）を1つ生成 ----
    def diameter(self, vl, bay, x_bay, c1, c2, cfg, bus_a, bus_b):
        sp, eqz = cfg["phase_sp"], cfg["eq_z"]
        yA, yB = cfg["busA"]["y"], cfg["busB"]["y"]
        margin = sp + 2.0
        pitch = (abs(yA - yB) - 2 * margin) / 8.0
        ys = [yA - margin - i * pitch for i in range(9)]  # 9 switches
        (y_LSA, y_CB1, y_LS1B, y_LS2A, y_CB2, y_LS2B, y_LS3A, y_CB3, y_LSB) = ys
        pre = f"{vl}_{bay}"

        def xp(ph):
            return x_bay + PHASE_IDX[ph] * sp

        # ノード
        n1 = self.node(f"{pre}_n1", vl, "section", bay=bay)
        n2 = self.node(f"{pre}_n2", vl, "section", bay=bay)
        t1 = self.node(f"{pre}_T1", vl, "tap", name=f"{bay} 北側回路引出点", bay=bay)
        n3 = self.node(f"{pre}_n3", vl, "section", bay=bay)
        n4 = self.node(f"{pre}_n4", vl, "section", bay=bay)
        t2 = self.node(f"{pre}_T2", vl, "tap", name=f"{bay} 南側回路引出点", bay=bay)
        n5 = self.node(f"{pre}_n5", vl, "section", bay=bay)
        n6 = self.node(f"{pre}_n6", vl, "section", bay=bay)

        new_bay = (c1 is None and c2 is None)
        nrm = "open" if new_bay else "closed"

        # 開閉器（母線側はパンタ式 LS）
        def pos(y):
            return (x_bay, y, eqz)
        self.switch(f"{pre}_LSA", "LS", bus_a, n1, nrm, bay=bay, pos=pos(y_LSA), subtype="パンタ式")
        self.switch(f"{pre}_CB1", "CB", n1, n2, nrm, bay=bay, pos=pos(y_CB1))
        self.switch(f"{pre}_LS1B", "LS", n2, t1, nrm, bay=bay, pos=pos(y_LS1B))
        self.switch(f"{pre}_LS2A", "LS", t1, n3, nrm, bay=bay, pos=pos(y_LS2A))
        self.switch(f"{pre}_CB2", "CB", n3, n4, nrm, bay=bay, pos=pos(y_CB2))
        self.switch(f"{pre}_LS2B", "LS", n4, t2, nrm, bay=bay, pos=pos(y_LS2B))
        self.switch(f"{pre}_LS3A", "LS", t2, n5, nrm, bay=bay, pos=pos(y_LS3A))
        self.switch(f"{pre}_CB3", "CB", n5, n6, nrm, bay=bay, pos=pos(y_CB3))
        self.switch(f"{pre}_LSB", "LS", n6, bus_b, nrm, bay=bay, pos=pos(y_LSB), subtype="パンタ式")

        # 接地開閉器（引出点と、遮断器両側の区間。点検用）
        self.es(f"{pre}_T1_ES", t1, pos=(x_bay + 1.0, (y_LS1B + y_LS2A) / 2, 1.5))
        self.es(f"{pre}_T2_ES", t2, pos=(x_bay + 1.0, (y_LS2B + y_LS3A) / 2, 1.5))
        for nid, y0, y1 in ((n1, y_LSA, y_CB1), (n2, y_CB1, y_LS1B), (n3, y_LS2A, y_CB2),
                            (n4, y_CB2, y_LS2B), (n5, y_LS3A, y_CB3), (n6, y_CB3, y_LSB)):
            self.es(f"{nid}_ES", nid, pos=(x_bay + 1.0, (y0 + y1) / 2, 1.5))

        if new_bay:
            # 新設ベイ：母線は延長済み。機器導体は未設置なので母線側ドロッパーのみ生成しない。
            return

        # 導体：母線ドロッパー（母線ノードに所属）
        for ph in PHASES:
            x = xp(ph)
            ya = yA - PHASE_IDX[ph] * sp   # 母線の相は y 方向に並ぶ
            yb = yB - PHASE_IDX[ph] * sp
            self.conductor(f"{pre}_dropA_{ph}", bus_a, ph, "dropper",
                           [(x, ya, cfg["busA"]["z"]), (x, ya, eqz), (x, y_LSA, eqz)])
            self.conductor(f"{pre}_dropB_{ph}", bus_b, ph, "dropper",
                           [(x, yb, cfg["busB"]["z"]), (x, yb, eqz), (x, y_LSB, eqz)])
            # 開閉器間の区間導体
            segs = [
                (n1, y_LSA, y_CB1), (n2, y_CB1, y_LS1B), (t1, y_LS1B, y_LS2A),
                (n3, y_LS2A, y_CB2), (n4, y_CB2, y_LS2B), (t2, y_LS2B, y_LS3A),
                (n5, y_LS3A, y_CB3), (n6, y_CB3, y_LSB),
            ]
            for nid, y0, y1 in segs:
                self.conductor(f"{nid}_{ph}", nid, ph, "equipment", [(x, y0, eqz), (x, y1, eqz)])

        # 引出回路（北側 c1 → T1, 南側 c2 → T2）
        self._circuit(vl, bay, x_bay, c1, t1, (y_LS1B + y_LS2A) / 2, "N", cfg)
        self._circuit(vl, bay, x_bay, c2, t2, (y_LS2B + y_LS3A) / 2, "S", cfg)

    def _circuit(self, vl, bay, x_bay, c, tap, y_tap, side, cfg):
        kind, cid, cname = c
        sp, eqz = cfg["phase_sp"], cfg["eq_z"]
        pre = f"{vl}_{cid}"
        if kind == "line":
            ln = self.node(f"{pre}", vl, "line", name=cname, bay=bay)
            self.switch(f"{pre}_LS", "LS", tap, ln, "closed", name=f"{cname} 線路断路器", bay=bay,
                        pos=(x_bay, y_tap, eqz))
            self.es(f"{pre}_ES", ln, name=f"{cname} 線路接地", pos=(x_bay - 1.0, y_tap, 1.5))
            self.source(f"SRC_{pre}", ln, cname)
            y_end = cfg["line_y"][0] if side == "N" else cfg["line_y"][1]
            for ph in PHASES:
                x = x_bay + PHASE_IDX[ph] * sp
                self.conductor(f"{pre}_{ph}", ln, ph, "line",
                               [(x, y_tap, eqz), (x, y_tap, cfg["line_z"] - 4.0), (x, y_end, cfg["line_z"])])
        elif kind == "tr":
            term = self.node(f"{pre}_{'HV' if vl == '220' else 'LV'}", vl, "transformer_terminal",
                             name=cname, bay=bay)
            self.switch(f"{pre}_{vl}_LS", "LS", tap, term, "closed", name=f"{cname} 断路器", bay=bay,
                        pos=(x_bay + 2.0, y_tap, eqz))
            self.es(f"{pre}_{vl}_ES", term, name=f"{cname} 接地", pos=(x_bay + 3.0, y_tap, 1.5))
            for ph in PHASES:
                x = x_bay + PHASE_IDX[ph] * sp
                self.conductor(f"{term}_{ph}", term, ph, "jumper",
                               [(x, y_tap, eqz), (x + cfg["tr_dx"], y_tap, eqz), (x + cfg["tr_dx"], y_tap, cfg["tr_z"])])
            self._tr.setdefault(cid, {})["hv" if vl == "220" else "lv"] = term
            self._tr[cid].setdefault("pos", (x_bay + cfg["tr_dx"], y_tap, 0.0))

    # ---- 構内（電圧階級）を1つ生成 ----
    def yard(self, vl):
        cfg = P[vl]
        bus_a = self.node(f"{vl}_BUSA", vl, "bus", name=f"{vl}kV A母線")
        bus_b = self.node(f"{vl}_BUSB", vl, "bus", name=f"{vl}kV B母線")
        self.es(f"{vl}_BUSA_ES", bus_a, name=f"{vl}kV A母線接地")
        self.es(f"{vl}_BUSB_ES", bus_b, name=f"{vl}kV B母線接地")

        n_bays = len(cfg["bays"])
        x_min = cfg["x0"] - cfg["bay_pitch"] / 2.0
        x_max = cfg["x0"] + cfg["bay_pitch"] * (n_bays - 0.5)
        sp = cfg["phase_sp"]
        for ph in PHASES:
            for bus, b in (("A", bus_a), ("B", bus_b)):
                y = cfg[f"bus{bus}"]["y"] - PHASE_IDX[ph] * sp
                z = cfg[f"bus{bus}"]["z"]
                self.conductor(f"{vl}_BUS{bus}_{ph}", b, ph, "bus", [(x_min, y, z), (x_max, y, z)], radius=0.03)

        for i, (bay, c1, c2) in enumerate(cfg["bays"]):
            self.diameter(vl, bay, cfg["x0"] + i * cfg["bay_pitch"], c1, c2, cfg, bus_a, bus_b)

        for i, y in enumerate(cfg["gw_y"]):
            self.structure(f"{vl}_GW_{'N' if i == 0 else 'S'}", "ground_wire",
                           [(x_min - 5.0, y, cfg["gw_z"]), (x_max + 5.0, y, cfg["gw_z"])],
                           name=f"{vl}kV 架空地線（{'北' if i == 0 else '南'}）", radius=0.01)

    def transformers(self):
        for tid, d in self._tr.items():
            self.m["transformers"].append({
                "id": tid, "hv_node": d["hv"], "lv_node": d["lv"], "mva": 300,
                "name": f"{tid} 220/66kV", "position": r3(d["pos"]),
            })

    def validate(self):
        ids = {}
        for key in ("nodes", "switches", "earth_switches", "sources", "transformers", "conductors", "structures"):
            for e in self.m[key]:
                assert e["id"] not in ids, f"duplicate id {e['id']} ({key} / {ids[e['id']]})"
                ids[e["id"]] = key
        nodes = {n["id"] for n in self.m["nodes"]}
        for s in self.m["switches"]:
            assert s["from"] in nodes and s["to"] in nodes, s
        for e in self.m["earth_switches"]:
            assert e["node"] in nodes, e
        for s in self.m["sources"]:
            assert s["node"] in nodes, s
        for t in self.m["transformers"]:
            assert t["hv_node"] in nodes and t["lv_node"] in nodes, t
        for c in self.m["conductors"]:
            assert c["node"] in nodes, c


def build():
    m = Model(P["name"])
    m.yard("220")
    m.yard("66")
    m.transformers()
    m.validate()
    return m.m


def main():
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "data" / "substation_fictional.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    model = build()
    out.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {k: len(v) for k, v in model.items() if isinstance(v, list)}
    print(f"wrote {out}")
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
