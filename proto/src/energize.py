#!/usr/bin/env python3
"""
充停電判定エンジン（MAAI）

構内モデル（schema/substation.schema.json）と開閉状態を受け取り、
各ノード・各導体の状態を返す。純粋なグラフ探索で、LLM は使わない。

状態:
  live             充電（電源に電気的につながっている）
  dead_grounded    停電かつ接地あり（作業可能な状態）
  dead_ungrounded  停電だが接地なし（検電・接地前。作業不可）
  FAULT_LIVE_GROUNDED  充電部に接地がついている（逆送の見落としなど。計画ミス）

使い方（CLI）:
  python3 src/energize.py data/substation_fictional.json                 # 常時状態
  python3 src/energize.py data/substation_fictional.json state.json      # 開閉状態を上書き

state.json の例:
  {"switches": {"220_D2_CB1": "open"}, "earth_switches": {"220_D2_T2_ES": "closed"}, "sources": {"SRC_220_FABLE1L": false}}
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field


LIVE = "live"
DEAD_G = "dead_grounded"
DEAD_U = "dead_ungrounded"
FAULT = "FAULT_LIVE_GROUNDED"


@dataclass
class SwitchingState:
    """開閉状態の上書き。指定がないものはモデルの normal / in_service に従う。"""
    switches: dict[str, str] = field(default_factory=dict)        # id -> "open"|"closed"
    earth_switches: dict[str, str] = field(default_factory=dict)  # id -> "open"|"closed"
    sources: dict[str, bool] = field(default_factory=dict)        # id -> in_service

    @classmethod
    def from_dict(cls, d: dict | None) -> "SwitchingState":
        d = d or {}
        return cls(dict(d.get("switches", {})), dict(d.get("earth_switches", {})), dict(d.get("sources", {})))


class _UF:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


@dataclass
class Result:
    node_state: dict[str, str]
    conductor_state: dict[str, str]
    groups: dict[str, list[str]]           # 代表ノード -> 同電位ノード一覧
    live_sources_by_node: dict[str, list[str]]  # ノード -> そのノードを充電している電源
    faults: list[str]                       # FAULT 状態のノード

    def summary(self) -> dict:
        counts = defaultdict(int)
        for s in self.node_state.values():
            counts[s] += 1
        return {"nodes": dict(counts), "faults": self.faults}


def energize(model: dict, state: SwitchingState | dict | None = None) -> Result:
    st = state if isinstance(state, SwitchingState) else SwitchingState.from_dict(state)

    node_ids = [n["id"] for n in model["nodes"]]
    uf = _UF(node_ids)

    # 開閉器: closed なら両端を連結
    for s in model["switches"]:
        pos = st.switches.get(s["id"], s["normal"])
        if pos not in ("open", "closed"):
            raise ValueError(f"switch {s['id']}: invalid position {pos!r}")
        if pos == "closed":
            uf.union(s["from"], s["to"])

    # 変圧器: 一次と二次は常に電気的に連結（逆送あり）
    for t in model["transformers"]:
        uf.union(t["hv_node"], t["lv_node"])

    # 電源
    live_roots: dict[str, list[str]] = defaultdict(list)
    for src in model["sources"]:
        on = st.sources.get(src["id"], src["in_service"])
        if on:
            live_roots[uf.find(src["node"])].append(src["id"])

    # 接地
    grounded_roots: set[str] = set()
    for es in model["earth_switches"]:
        pos = st.earth_switches.get(es["id"], es["normal"])
        if pos == "closed":
            grounded_roots.add(uf.find(es["node"]))

    node_state: dict[str, str] = {}
    groups: dict[str, list[str]] = defaultdict(list)
    live_by_node: dict[str, list[str]] = {}
    faults: list[str] = []
    for nid in node_ids:
        r = uf.find(nid)
        groups[r].append(nid)
        is_live = r in live_roots
        is_g = r in grounded_roots
        if is_live and is_g:
            s = FAULT
            faults.append(nid)
        elif is_live:
            s = LIVE
        elif is_g:
            s = DEAD_G
        else:
            s = DEAD_U
        node_state[nid] = s
        if is_live:
            live_by_node[nid] = sorted(live_roots[r])

    conductor_state = {c["id"]: node_state[c["node"]] for c in model["conductors"]}
    return Result(node_state, conductor_state, dict(groups), live_by_node, sorted(faults))


# --------------------------------------------------------------------------
# 便利関数
# --------------------------------------------------------------------------
def bay_switch_ids(model: dict, bay: str, voltage: str | None = None) -> list[str]:
    return [s["id"] for s in model["switches"]
            if s.get("bay") == bay and (voltage is None or s["from"].startswith(f"{voltage}_") or s["to"].startswith(f"{voltage}_"))]


def live_conductors(model: dict, res: Result, exposed_only: bool = False) -> list[dict]:
    """充電導体の一覧。

    exposed_only=True は離隔判定用：露出導体だけを返す（GIS内部導体 exposed=false を除く）。
    3D表示は exposed_only=False で全部を受け取り、GIS内部は色だけ変えて描く。
    """
    out = []
    for c in model["conductors"]:
        if res.conductor_state[c["id"]] != LIVE:
            continue
        if exposed_only and not c.get("exposed", True):
            continue
        out.append(c)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    model = json.load(open(argv[1], encoding="utf-8"))
    state = json.load(open(argv[2], encoding="utf-8")) if len(argv) > 2 else None
    res = energize(model, state)
    out = {
        "summary": res.summary(),
        "node_state": res.node_state,
        "live_conductor_count": len(live_conductors(model, res)),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if res.faults else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
