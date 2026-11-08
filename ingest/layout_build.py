"""結線図（topology）と、装置図から読んだ位置・高さ（ingest/pdf_layout.extract_layout の返り値）から、
3D レイアウト（truth/layout.json と同じ契約）を組み立て直す。決定論。Claude は呼ばない。

  build_layout(topology, extracted)        → layout の dict（"source": "drawing-draft"）
  check_consistency(topology, extracted)   → 三面（結線図・平面・断面）の照合結果
  match_equipment(sld_numbers, plan_numbers) → 単線結線図の機器一覧と平面の機器番号の一致（台数と差分）
  to_contract(layout)                      → contracts/layout.schema.json に通る形（下書きの印を外す）

位置と高さは必ず extracted から取る（synth.gen_site.P は使わない）。図面に無いものは synth/equipment.py の寸法表
（"height_source": "library"）で補う。導体は gen_site.py と同じ作り方（相ごとの折れ線のカプセル）で、
両端の機器が平面に見つからない導体は作らない（充電扱いにもしない。questions に出す）。
鉄構・架空地線・鉄塔は、母線の範囲・断面の高さラベルから truth と同じ規則で組む（下の _GANTRY_RULES）。
"""
from __future__ import annotations

import re

from synth.equipment import EQUIP, LINE_GANTRY_220, TOWER_220, TRANSFORMER, terminal_z
from synth.gen_site import BUS_R, PHASE_IDX, PHASES, Site     # 組み立ての道具だけ。P は使わない

# 鉄構などの規則（gen_site.py と同じ仮定値）
_GANTRY_RULES = {
    "220_line_margin": 6.0,     # 220kV 引留鉄構・架空地線は母線の両端から 6 m 外まで
    "220_bus_gantry_dz": 1.0,   # 母線鉄構（母線の両端、母線と直角）の梁は母線の 1.0 m 上
    "220_bus_gantry_half": 3.0, # 母線鉄構の柱は外側の相から 3 m 外
    "sec_rise": 2.0,            # セクション断路器の碍管の頭から母線の高さへ 2 m で上がる
    "66_gantry_margin": 4.0,    # 66kV 引留鉄構は母線の両端から 4 m 外まで（架空地線は 5 m）
    "66_gw_margin": 5.0,
    "66_bus_gantry_spacing": 14.0,
    "sec_gap": 0.6,             # 母線上のセクション断路器の両側で母線を 0.6 m 切る
    "pantograph_gap": 0.6,      # パンタ型断路器の柱頭から遮断器側の導体は 0.6 m だけ y をずらして始める
    "es_z": 1.5,                # 接地開閉器の記号位置の高さ（図面に高さラベルが無い）
}
_KINDS_WITH_NUMBER = ("disconnector", "breaker", "earthing", "transformer", "load")


def _label_of(n: dict) -> str:
    return n.get("number") or n.get("name", "")


def _default_z(node: dict) -> float:
    kv = node.get("voltage_kv") or 220
    k = node["kind"]
    if k == "disconnector":
        return terminal_z(kv)
    if k == "breaker":
        return EQUIP[kv]["cb_terminal_z"]
    if k == "earthing":
        return _GANTRY_RULES["es_z"]
    return 0.0       # 変圧器・調相設備は地上


# --------------------------------------------------------------------------
# 三面の照合
# --------------------------------------------------------------------------
def check_consistency(topology: dict, extracted: dict) -> list[dict]:
    """結線図・平面・断面の照合。{"kind": "missing_in_plan" | "missing_in_sld" | "no_height", "id", "message"} の列。
    no_height は既定値で補うので注意扱い（"severity": "注意"）。"""
    out: list[dict] = []
    nodes = {n["id"]: n for n in topology["nodes"] if n["kind"] in _KINDS_WITH_NUMBER and _label_of(n)}
    plan_labels = {a["number"] for a in extracted["apparatus"]}
    height_ids = {h["element_id"] for h in extracted["heights"]}
    for nid, n in nodes.items():
        label = _label_of(n)
        if label not in plan_labels:
            out.append({"kind": "missing_in_plan", "id": nid, "severity": "要確認",
                        "message": f"結線図の {label}（{nid}）が平面に無い。導体の端が決まらないので、この機器の位置は決まらない"})
    sld_labels = {_label_of(n) for n in nodes.values()}
    for a in extracted["apparatus"]:
        if a["number"] not in sld_labels:
            out.append({"kind": "missing_in_sld", "id": a["number"], "severity": "要確認",
                        "message": f"平面の {a['number']} が結線図に無い。機器の種類が決まらないので配置に入れない"})
    for u in extracted.get("unmatched_numbers", []):
        out.append({"kind": "missing_in_sld", "id": u["number"], "severity": "要確認",
                    "message": f"平面の文字 {u['number']} が結線図に無い。機器の種類が決まらないので配置に入れない"})
    for a in extracted["apparatus"]:
        n = next((x for x in nodes.values() if _label_of(x) == a["number"]), None)
        if n is None or a["number"] in height_ids:
            continue
        out.append({"kind": "no_height", "id": n["id"], "severity": "注意",
                    "message": f"{a['number']}（{n['id']}）の高さラベルが断面に無い。寸法表の既定値 {_default_z(n):g} m で補う"})
    return out


_KIND_JA = {"disconnector": "断路器", "breaker": "遮断器", "earthing": "接地開閉器", "transformer": "変圧器", "load": "調相設備"}


def topology_numbers(topology: dict) -> list[str]:
    """topology の番号つき機器（開閉器・遮断器・接地開閉器・変圧器・調相設備）の図面上の文字の一覧。"""
    return sorted({_label_of(n) for n in topology["nodes"] if n["kind"] in _KINDS_WITH_NUMBER and _label_of(n)})


def match_equipment(sld_numbers, plan_numbers) -> dict:
    """単線結線図で作った機器一覧と、平面（装置図 1/400）の機器番号が一致しているか。決定論。

    返り値: {"sld": 単線図の台数, "plan": 平面の台数, "matched": 両方にある台数, "ok": 完全一致か,
             "only_sld": 単線図だけにある番号, "only_plan": 平面だけにある番号, "by_kind": 種類ごとの台数}
    """
    from ingest.pdf_layout import _guess_symbol
    s, p = set(sld_numbers), set(plan_numbers)
    by_kind: dict[str, dict] = {}
    for label, side in ((s, "sld"), (p, "plan")):
        for num in label:
            g = _guess_symbol(num)
            k = _KIND_JA.get(g["node_kind"], g["node_kind"]) if g else "不明"
            by_kind.setdefault(k, {"sld": 0, "plan": 0})[side] += 1
    return {"sld": len(s), "plan": len(p), "matched": len(s & p), "ok": s == p,
            "only_sld": sorted(s - p), "only_plan": sorted(p - s), "by_kind": by_kind}


# --------------------------------------------------------------------------
# 組み立て
# --------------------------------------------------------------------------
class _Ctx:
    def __init__(self, topology: dict, extracted: dict):
        self.topo = topology
        self.ex = extracted
        self.nodes = {n["id"]: n for n in topology["nodes"]}
        self.edges = topology["edges"]
        self.questions: list[str] = []
        self.site = Site(topology.get("name", ""))
        # 番号 → ノード
        self.by_label: dict[str, dict] = {}
        for n in topology["nodes"]:
            if n["kind"] in _KINDS_WITH_NUMBER and _label_of(n):
                self.by_label.setdefault(_label_of(n), n)
        # 機器の位置 (x, y, z) と高さの出どころ
        self.pos: dict[str, tuple[float, float, float]] = {}
        self.hsrc: dict[str, str] = {}
        self.heights: dict[str, dict] = {}      # element_id（番号または構造物 id）→ {z_m, y_m, section}
        for h in extracted["heights"]:
            self.heights.setdefault(h["element_id"], h)
        self.arresters = list(extracted.get("arresters", []))
        self._place()

    def ask(self, text: str):
        if text not in self.questions:
            self.questions.append(text)

    def _place(self):
        import ingest.pdf_layout as pl
        from synth import drawing_rules as dr
        for a in self.ex["apparatus"]:
            n = self.nodes.get(a.get("id")) if a.get("id") else self.by_label.get(a["number"])
            if n is None:
                continue                      # 結線図に無い番号は配置に入れない（check_consistency が知らせる）
            x, y = a["at"]
            if a.get("id") is None:
                # 結線図が無いまま読んだ下書き: 結線図の kind で文字から中心を戻し直す
                sym = pl._symbol_from_topology(n)
                if sym["kind"] != a["kind"] or sym["along"] != a["along"]:
                    x, y = dr.center_from_text(sym["kind"], a["text_xy_mm"], sym["along"])
                    self.ask(f"{a['number']}: 番号の形から推定した種類（{a['kind']}）が結線図（{sym['kind']}）と違うので、結線図の種類で中心を戻し直した")
            h = self.heights.get(a["number"])
            if h is not None and n["kind"] in ("disconnector", "breaker", "earthing", "load"):
                z, src = h["z_m"], "drawing"
            elif n["kind"] == "disconnector" and dr.orientation(n["id"])["along"] == "x" and self.bus(n.get("voltage_kv") or 220, 1):
                z, src = self.bus(n.get("voltage_kv") or 220, 1)["z_m"], "drawing"    # 母線上のセクション断路器は母線の高さ（母線のラベルから）
            else:
                z, src = _default_z(n), "library"      # 変圧器の高さラベルは一次ブッシングの頂部（at の z ではない）
            self.pos[n["id"]] = (float(x), float(y), float(z))
            self.hsrc[n["id"]] = src

    # ---- 結線図の隣 ----
    def neighbor(self, port: str) -> str | None:
        for e in self.edges:
            if e["from"] == port:
                return e["to"]
            if e["to"] == port:
                return e["from"]
        return None

    def edge_id(self, a: str, b: str) -> str | None:
        for e in self.edges:
            if {e["from"], e["to"]} == {a, b}:
                return e["id"]
        return None

    def need(self, ids: list[str], what: str) -> bool:
        miss = [i for i in ids if i not in self.pos]
        if miss:
            self.ask(f"{what}の導体を作らない: 平面に位置が読めていない機器 {', '.join(miss)}")
            return False
        return True

    def bus(self, kv: int, no: int) -> dict | None:
        return next((b for b in self.ex["buses"] if b["kv"] == kv and b["no"] == no), None)

    def element(self, eid: str) -> dict | None:
        return self.heights.get(eid)


def _cap(c: _Ctx, iid: str, ph: str, pts: list[tuple], r: float = 0.02):
    c.site.capsules(iid, ph, pts, r=r)


def _ph_x(x: float, ph: str, sp: float) -> float:
    return x + PHASE_IDX[ph] * sp


def _find_arrester(c: _Ctx, x_bay: float, sp: float, y_range: tuple[float, float]) -> float | None:
    """ベイの x の列にある避雷器の y。見つかれば c.arresters から外さずに y だけ返す。"""
    for a in c.arresters:
        if abs(a["x_t"] - sp - x_bay) < 0.05 and y_range[0] <= a["y"] <= y_range[1]:
            return a["y"]
    return None


def _yard_220(c: _Ctx):
    sp = EQUIP[220]["phase_sp"]
    bus = c.bus(220, 1)
    if bus is None or not bus.get("x_range_m"):
        c.ask("220kV 母線の高さまたは範囲が読めていない。220kV の導体を作らない")
        return
    by, bz = bus.get("plan_y_m") or bus["y_m"], bus["z_m"]
    bx0, bx1 = bus["x_range_m"]
    bus_nodes = sorted(i for i, n in c.nodes.items() if n["kind"] == "bus" and n.get("voltage_kv") == 220)
    secs = sorted((i for i, n in c.nodes.items() if re.fullmatch(r"220-SEC-[A-Z]{2}", i) and i in c.pos), key=lambda i: c.pos[i][0])
    pitch2 = EQUIP[220]["cb"]["bushing_pitch"] / 2
    dsec = EQUIP[220]["ds_sec"]; sec_half = dsec["span"] / 2; sec_top = dsec["column"] + dsec["insulator"] + 0.15
    rise = _GANTRY_RULES["sec_rise"]
    if len(secs) == len(bus_nodes) - 1:
        xs = [bx0] + [c.pos[s][0] for s in secs] + [bx1]
        for i, b in enumerate(bus_nodes):
            for ph in PHASES:
                y = by - PHASE_IDX[ph] * sp
                # gen_site と同じ規則: 両端は母線鉄構から水平、セクション断路器の側は碍管の頭へ少し下りる
                pts = [(xs[i] + sec_half, y, sec_top), (xs[i] + sec_half + rise, y, bz)] if i > 0 else [(xs[i], y, bz)]
                pts += [(xs[i + 1] - sec_half - rise, y, bz), (xs[i + 1] - sec_half, y, sec_top)] if i < len(bus_nodes) - 1 else [(xs[i + 1], y, bz)]
                _cap(c, b, ph, pts, r=BUS_R)
    else:
        c.ask(f"220kV 母線 {len(bus_nodes)} 区間に対しセクション断路器が {len(secs)} 台しか読めていない。母線の水平部を作らない")

    g = c.element("220-GANTRY-LINE")
    gw = c.element("220-GW-N")
    tw = c.element("220-TOWER-E1")
    # ---- 線路ベイ ----
    for ls in sorted(i for i in c.nodes if re.fullmatch(r"220-L\d+-LS", i)):
        pre = ls[:-3]
        idx = pre.split("-L")[-1]
        cb, bls, n1, n2 = f"{pre}-CB", f"{pre}-BLS", f"{pre}-N1", f"{pre}-N2"
        ln = next((i for i, n in c.nodes.items() if n["kind"] == "source" and n.get("voltage_kv") == 220 and n.get("bay") == f"L{idx}"), None)
        bsec = next((nb for nb in (c.neighbor(f"{bls}.a"), c.neighbor(f"{bls}.b")) if nb in c.nodes and c.nodes[nb]["kind"] == "bus"), None)
        if c.need([ls, cb, bls], f"220kV 線路ベイ {pre}"):
            x, y_ls, z_ls = c.pos[ls]; _, y_cb, z_cb = c.pos[cb]; _, y_bls, z_bls = c.pos[bls]
            for ph in PHASES:
                px = _ph_x(x, ph, sp); yp = by - PHASE_IDX[ph] * sp
                _cap(c, n1, ph, [(px, y_ls, z_ls), (px, y_cb + pitch2, z_cb)])
                _cap(c, n2, ph, [(px, y_cb - pitch2, z_cb), (px, yp + _GANTRY_RULES["pantograph_gap"], z_bls)])
                if bsec:
                    _cap(c, bsec, ph, [(px, yp, z_bls), (px, yp, bz)])
                if ln and g and tw:
                    _cap(c, ln, ph, [(px, y_ls + 1.0, z_ls), (px, g["y_m"], g["z_m"]), (px, tw["y_m"], tw["z_m"])])
            if ln and not (g and tw):
                c.ask(f"{pre}: 引留鉄構または引留鉄塔の高さラベルが断面に無く、線路 {ln} の導体を作らない")
            la_y = _find_arrester(c, x, sp, (y_ls, 200.0))
            if la_y is not None:
                c.site.apparatus(f"{pre}-LA", "la", 220, x, la_y, f"{c.nodes[ln]['name'] if ln else pre} 避雷器")
    # ---- 変圧器ベイ ----
    for bls in sorted(i for i in c.nodes if re.fullmatch(r"220-T\d+-BLS", i)):
        pre = bls[:-4]
        n = pre.split("-T")[-1]
        cb, ls, n1, n2, hv, tr = f"{pre}-CB", f"{pre}-LS", f"{pre}-N1", f"{pre}-N2", f"220-TR-{n}-HV", f"TR-{n}"
        bsec = next((nb for nb in (c.neighbor(f"{bls}.a"), c.neighbor(f"{bls}.b")) if nb in c.nodes and c.nodes[nb]["kind"] == "bus"), None)
        if not c.need([bls, cb, ls, tr], f"220kV 変圧器ベイ {pre}"):
            continue
        x, y_bls, z_bls = c.pos[bls]; _, y_cb, z_cb = c.pos[cb]; _, y_ls, z_ls = c.pos[ls]
        tr_y = c.pos[tr][1]
        label = _label_of(c.nodes[tr])
        hv_top = c.element(label)["z_m"] if c.element(label) else TRANSFORMER["hv"]["top_z"]
        la_y = _find_arrester(c, x, sp, (0.0, y_ls))
        for ph in PHASES:
            px = _ph_x(x, ph, sp); yp = by - PHASE_IDX[ph] * sp
            bx = _ph_x(x, ph, 0) + PHASE_IDX[ph] * TRANSFORMER["hv_pitch"]
            if bsec:
                _cap(c, bsec, ph, [(px, yp, bz), (px, yp, z_bls)])
            _cap(c, n1, ph, [(px, yp - _GANTRY_RULES["pantograph_gap"], z_bls), (px, y_cb + pitch2, z_cb)])
            _cap(c, n2, ph, [(px, y_cb - pitch2, z_cb), (px, y_ls, z_ls)])
            pts = [(px, y_ls, z_ls)] + ([(px, la_y, z_ls)] if la_y is not None else []) + [(bx, tr_y + TRANSFORMER["hv"]["y"], hv_top)]
            _cap(c, hv, ph, pts)
        if la_y is not None:
            c.site.apparatus(f"{pre}-LA", "la", 220, x, la_y, f"{n}号変圧器 一次 避雷器")
        else:
            c.ask(f"{pre}: 避雷器が平面に見つからず、一次の導体は避雷器を通さずに引く")

    # ---- 引留鉄構・架空地線・鉄塔・母線鉄構 ----
    if g and gw:
        m = _GANTRY_RULES["220_line_margin"]
        yg = g["y_m"]
        c.site.structure("220-GW-N", "ground_wire", [(bx0 - m, yg, gw["z_m"]), (bx1 + m, yg, gw["z_m"])], name="220kV 架空地線（北）")
        c.site.gantry("220-GANTRY-LINE", bx0 - m, bx1 + m, yg, LINE_GANTRY_220["column"], "220kV 引留鉄構（北）", beam_z=g["z_m"])
    else:
        c.ask("220kV の引留鉄構または架空地線の高さラベルが断面に無い。鉄構・架空地線を作らない")
    if tw:
        for src in sorted(i for i, n in c.nodes.items() if n["kind"] == "source" and n.get("voltage_kv") == 220):
            lsx = next((c.pos[f"{p}-LS"][0] for p in [f"220-L{c.nodes[src]['bay'][1:]}"] if f"{p}-LS" in c.pos), None)
            if lsx is None:
                continue
            cid = src.split("-")[-1]
            c.site.layout["structures"].append({"id": f"220-TOWER-{cid}", "kind": "other", "name": f"{c.nodes[src]['name']} 引留鉄塔（構外）",
                                                "primitives": [{"type": "capsule", "a": [round(lsx, 3), round(tw["y_m"], 3), 0.0],
                                                                "b": [round(lsx, 3), round(tw["y_m"], 3), TOWER_220["height"]], "r": 1.0}]})
    else:
        c.ask("引留鉄塔の高さラベルが断面に無い。鉄塔を作らない")
    hw = sp + _GANTRY_RULES["220_bus_gantry_half"]
    for end, x in (("W", bx0), ("E", bx1)):
        c.site.gantry_y(f"220-GANTRY-BUS-{end}", x, by - hw, by + hw, bz + _GANTRY_RULES["220_bus_gantry_dz"], f"220kV 母線鉄構（{'西' if end == 'W' else '東'}）")


def _yard_66(c: _Ctx):
    sp = EQUIP[66]["phase_sp"]
    busA, busB = c.bus(66, 1), c.bus(66, 2)
    bays = sorted((m.group(1) for i in c.nodes if (m := re.fullmatch(r"66-(D\d+)-LSA", i))), key=lambda d: int(d[1:]))
    if busA is None or busB is None or not bays or not all(f"66-{d}-LSA" in c.pos for d in bays):
        c.ask("66kV 母線の高さ、またはダイヤの位置が読めていない。66kV の導体を作らない")
        return
    xb = [c.pos[f"66-{d}-LSA"][0] for d in bays]
    if len(xb) >= 2:
        pitch = (xb[-1] - xb[0]) / (len(xb) - 1)
        x_min, x_max = xb[0] - pitch / 2, xb[-1] + pitch / 2
    else:
        x_min, x_max = busA["x_range_m"][0] + 1.0, busA["x_range_m"][1] - 1.0
        c.ask("66kV のダイヤが 1 つしか読めず、母線の端は平面の太線から 1 m 内側とした")
    yA, zA = busA.get("plan_y_m") or busA["y_m"], busA["z_m"]
    yB, zB = busB.get("plan_y_m") or busB["y_m"], busB["z_m"]
    for ph in PHASES:
        _cap(c, "66-BUS-A", ph, [(x_min, yA - PHASE_IDX[ph] * sp, zA), (x_max, yA - PHASE_IDX[ph] * sp, zA)], r=BUS_R)
        _cap(c, "66-BUS-B", ph, [(x_min, yB - PHASE_IDX[ph] * sp, zB), (x_max, yB - PHASE_IDX[ph] * sp, zB)], r=BUS_R)
    ng, lg, gw = c.element("66-GANTRY-N"), c.element("66-GANTRY-LINE"), c.element("66-GW-S")
    lv_z = TRANSFORMER["lv"]["top_z"]

    for d in bays:
        pre = f"66-{d}"
        sw = {k: f"{pre}-{k}" for k in ("LSA", "CB1", "LS1B", "LS2A", "CB2", "LS2B", "LS3A", "CB3", "LSB")}
        taps = {"T1": f"{pre}-T1", "T2": f"{pre}-T2"}
        circuits = {}
        for tk, tid in taps.items():
            for e in c.edges:
                other = e["to"] if e["from"] == tid else e["from"] if e["to"] == tid else None
                if other and other.endswith(".a") and other[:-2] not in sw.values():
                    circuits[tk] = other[:-2]
        if not circuits:
            continue                                     # 新設予定のダイヤ（機器未接続）: 導体なし
        if not c.need(list(sw.values()), f"66kV ダイヤ {d}"):
            continue
        x = c.pos[sw["LSA"]][0]
        ys = {k: c.pos[v][1] for k, v in sw.items()}
        eqz = c.pos[sw["LSA"]][2]
        drop_a = c.edge_id(f"66-BUS-A", f"{sw['LSA']}.a")
        drop_b = c.edge_id(f"66-BUS-B", f"{sw['LSB']}.b")
        segs = {"N1": ("LSA", "CB1"), "N2": ("CB1", "LS1B"), "T1": ("LS1B", "LS2A"), "N3": ("LS2A", "CB2"), "N4": ("CB2", "LS2B"),
                "T2": ("LS2B", "LS3A"), "N5": ("LS3A", "CB3"), "N6": ("CB3", "LSB")}
        for ph in PHASES:
            px = _ph_x(x, ph, sp)
            ya, yb = yA - PHASE_IDX[ph] * sp, yB - PHASE_IDX[ph] * sp
            if drop_a:
                _cap(c, drop_a, ph, [(px, ya, zA), (px, ya, eqz), (px, ys["LSA"], eqz)])
            if drop_b:
                _cap(c, drop_b, ph, [(px, yb, zB), (px, yb, eqz), (px, ys["LSB"], eqz)])
            for k, (s0, s1) in segs.items():
                if f"{pre}-{k}" in c.nodes:
                    _cap(c, f"{pre}-{k}", ph, [(px, ys[s0], eqz), (px, ys[s1], eqz)])
        for tk, lsid in circuits.items():
            if lsid not in c.pos:
                c.ask(f"66kV {d} の回路の断路器 {lsid} が平面に無い。この回路の導体を作らない")
                continue
            y_tap = c.pos[lsid][1]
            m_line = re.fullmatch(r"66-LINE-(\w+)-LS", lsid)
            m_tr = re.fullmatch(r"66-TR-(\d+)-LS", lsid)
            m_load = re.fullmatch(r"66-((?:SC|SR)-\d+)-LS", lsid)
            if m_line:
                ln = f"66-LINE-{m_line.group(1)}"
                if not lg:
                    c.ask(f"南の引留鉄構の高さラベルが断面に無く、{ln} の導体を作らない")
                    continue
                for ph in PHASES:
                    px = _ph_x(x, ph, sp)
                    _cap(c, ln, ph, [(px, y_tap, eqz), (px, y_tap, lg["z_m"] - 3.0), (px, lg["y_m"], lg["z_m"])])
                la_y = _find_arrester(c, x, sp, (0.0, lg["y_m"] + 10.0))
                if la_y is not None:
                    c.site.apparatus(f"{ln}-LA", "la", 66, x, la_y, f"{c.nodes[ln]['name']} 避雷器")
            elif m_tr:
                n = m_tr.group(1)
                term, tr = f"66-TR-{n}-LV", f"TR-{n}"
                if not ng or tr not in c.pos:
                    c.ask(f"北の引留鉄構の高さラベル、または変圧器 {tr} の位置が読めず、{term} の導体を作らない")
                    continue
                x_tr, y_tr0 = c.pos[tr][0], c.pos[tr][1]
                y_tr = y_tr0 + TRANSFORMER["lv"]["y"]
                for ph in PHASES:
                    px = _ph_x(x, ph, sp)
                    xt = _ph_x(x_tr, ph, sp)
                    xbp = x_tr + PHASE_IDX[ph] * TRANSFORMER["lv_pitch"]
                    _cap(c, term, ph, [(px, y_tap, eqz), (px, y_tap, ng["z_m"] - 3.0), (px, ng["y_m"], ng["z_m"]),
                                       (xt, ng["y_m"] + 1.0, ng["z_m"]), (xbp, y_tr, lv_z)])
            elif m_load:
                lid = f"66-{m_load.group(1)}"
                if not ng or lid not in c.pos:
                    c.ask(f"北の引留鉄構の高さラベル、または調相設備 {lid} の位置が読めず、導体を作らない")
                    continue
                load_y = c.pos[lid][1]
                for ph in PHASES:
                    px = _ph_x(x, ph, sp)
                    _cap(c, lid, ph, [(px, y_tap, eqz), (px, y_tap, ng["z_m"] - 3.0), (px, ng["y_m"], ng["z_m"]), (px, load_y, eqz)])
            else:
                c.ask(f"66kV {d} の回路 {lsid} の種類が分からず、導体を作らない")

    m66, mgw = _GANTRY_RULES["66_gantry_margin"], _GANTRY_RULES["66_gw_margin"]
    if gw and lg:
        c.site.structure("66-GW-S", "ground_wire", [(x_min - mgw, lg["y_m"], gw["z_m"]), (x_max + mgw, lg["y_m"], gw["z_m"])], name="66kV 架空地線（南）")
    if lg:
        c.site.gantry("66-GANTRY-LINE", x_min - m66, x_max + m66, lg["y_m"], lg["z_m"], "66kV 引留鉄構（南）")
    if ng:
        c.site.gantry("66-GANTRY-N", x_min - m66, x_max + m66, ng["y_m"], ng["z_m"], "66kV 引留鉄構（北・変圧器二次/調相）")
    if not (gw and lg and ng):
        c.ask("66kV の引留鉄構または架空地線の高さラベルが断面に無い。無いものは作らない")
    sp_b = _GANTRY_RULES["66_bus_gantry_spacing"]
    c.site.gantry("66-GANTRY-BUS-A", x_min, x_max, yA, zA + 1.5, "66kV 1号母線鉄構", spacing=sp_b)
    c.site.gantry("66-GANTRY-BUS-B", x_min, x_max, yB, zB + 1.5, "66kV 2号母線鉄構", spacing=sp_b)


def build_layout(topology: dict, extracted: dict) -> dict:
    """結線図 ＋ 装置図から読んだ位置・高さ → 3D レイアウト。truth/layout.json と同じ形（下書きの印つき）。

    各 item の "at" は [x, y, z]。z は断面の高さラベル（"height_source": "drawing"）、無ければ寸法表の既定値（"library"）。
    返り値に "source": "drawing-draft" と "questions" を含む。契約（layout.schema.json）に通すには to_contract() を使う。
    """
    c = _Ctx(topology, extracted)
    # 機器（at と高さの出どころ）
    for a in extracted["apparatus"]:
        n = c.nodes.get(a.get("id")) if a.get("id") else c.by_label.get(a["number"])
        if n is None or n["id"] not in c.pos:
            continue
        it = c.site.item(n["id"], at=c.pos[n["id"]])
        it["height_source"] = c.hsrc[n["id"]]
    _yard_220(c)
    _yard_66(c)
    # 結線図と平面・断面の照合の結果を質問にまとめる
    findings = check_consistency(topology, extracted)
    for f in findings:
        if f["kind"] != "no_height":
            c.ask(f["message"])
    n_nh = sum(1 for f in findings if f["kind"] == "no_height")
    if n_nh:
        c.ask(f"高さラベルの無い機器 {n_nh} 件は寸法表の既定値で補った（\"height_source\": \"library\"）。断面に高さを足せるか確かめること")
    for q in extracted.get("questions", []):
        if "が平面に見つからない" not in q:        # 上の照合（missing_in_plan）と同じ内容
            c.ask(q)

    lay = c.site.layout
    lay.update({
        "site_id": topology.get("site_id", lay.get("site_id")),
        "generated_by": "ingest/layout_build.py",
        "origin_note": "装置図の平面の原点（構内 (0,0)）を P1 とする。X=東, Y=北, Z=上（仮定）",
        "notes": ["装置図（平面 1/400・断面 A-A/B-B/C-C）から読み直した下書き。人の確認が済むまで正式な配置として扱わない。",
                  "高さは断面の高さラベルを優先し、無いものは寸法表（synth/equipment.py）の既定値。"],
        "reference_points": [{"id": "P1", "x": 0.0, "y": 0.0, "z": 0.0, "note": "装置図平面の原点"}],
        "source": "drawing-draft",
        "questions": c.questions,
    })
    return lay


_DRAFT_ITEM_KEYS = ("height_source",)


def to_contract(layout: dict) -> dict:
    """下書きの印（source・questions・item の height_source）を外し、contracts/layout.schema.json に通る形にする。"""
    out = {k: v for k, v in layout.items() if k not in ("source", "questions")}
    out["items"] = [{k: v for k, v in it.items() if k not in _DRAFT_ITEM_KEYS} for it in layout["items"]]
    return out
