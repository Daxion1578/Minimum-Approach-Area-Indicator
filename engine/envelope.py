"""安全包絡（§7.3）。課電判定の結果と配置から、近づいてはいけない領域をカプセルで作る。

半径 = 導体半径 + 離隔距離。離隔は `data/tables/clearance.csv`（電圧階級 → m、出典列つき、既定値は「要確認」）。
保守側の既定: treat_ungrounded_as_live=True（未接地の停止区間も包絡を作る）。
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from engine.energize import DEAD_UNGROUNDED, INVALID, LIVE, Energization
from engine.topology import Topology

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLE = ROOT / "data" / "tables" / "clearance.csv"


@dataclass(frozen=True)
class ClearanceRow:
    voltage_kv_max: float
    clearance_m: float
    per_10kv_above_60_m: float
    source: str
    status: str


class ClearanceTable:
    def __init__(self, rows: list[ClearanceRow], table_id: str):
        self.rows = sorted(rows, key=lambda r: r.voltage_kv_max)
        self.table_id = table_id

    @classmethod
    def load(cls, path: str | Path = DEFAULT_TABLE, table_id: str = "default-jp") -> "ClearanceTable":
        rows = []
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r["table_id"] != table_id:
                    continue
                rows.append(ClearanceRow(float(r["voltage_kv_max"]), float(r["clearance_m"]),
                                         float(r["per_10kv_above_60_m"]), r["source"], r["status"]))
        if not rows:
            raise ValueError(f"clearance table {table_id!r} not found in {path}")
        return cls(rows, table_id)

    def clearance(self, voltage_kv: float) -> tuple[float, ClearanceRow]:
        for r in self.rows:
            if voltage_kv <= r.voltage_kv_max:
                extra = 0.0
                if r.per_10kv_above_60_m and voltage_kv > 60:
                    extra = math.ceil((voltage_kv - 60) / 10) * r.per_10kv_above_60_m
                return round(r.clearance_m + extra, 3), r
        raise ValueError(f"no clearance row for {voltage_kv} kV")


def _voltage_of(topo: Topology, item_id: str) -> float | None:
    n = topo.nodes.get(item_id)
    if n is not None:
        if n.kind == "transformer":
            return None
        return n.voltage_kv
    for e in topo.edges:
        if e.id == item_id:
            a = topo.node_of(e.a)
            return a.voltage_kv if a.kind != "transformer" else topo.node_of(e.b).voltage_kv
    return None


def _conductor_of(topo: Topology, item_id: str) -> str:
    for e in topo.edges:
        if e.id == item_id:
            return e.conductor
    return "bare"  # ノードのカプセルは露出導体として扱う（GIS 内部は辺 enclosed で表す）


def envelopes(topo: Topology, layout: dict, res: Energization, table: ClearanceTable | None = None,
              treat_ungrounded_as_live: bool = True, step: int | None = None) -> dict:
    """§6.5 envelope.json（承認前なので approved は無し）。"""
    table = table or ClearanceTable.load()
    states = {LIVE, INVALID}
    if treat_ungrounded_as_live:
        states.add(DEAD_UNGROUNDED)
    out = []
    for it in layout["items"]:
        if not it["primitives"]:
            continue
        try:
            s = res.state_of(it["id"])
        except KeyError:
            continue
        if s not in states or _conductor_of(topo, it["id"]) != "bare":
            continue
        kv = _voltage_of(topo, it["id"])
        if kv is None:
            continue
        c, row = table.clearance(kv)
        for p in it["primitives"]:
            out.append({
                "conductor_id": it["id"], "voltage_kv": kv, "clearance_m": c, "state": s,
                "clearance_status": row.status,
                "primitive": {"type": "capsule", "a": p["a"], "b": p["b"], "r": round(p["r"] + c, 3), "phase": p.get("phase")},
            })
    return {
        "schema_version": "0.1", "site_id": topo.site_id, "step": res.step if step is None else step,
        "clearance_table_id": table.table_id,
        "treat_ungrounded_as_live": treat_ungrounded_as_live,
        "envelopes": out,
    }
