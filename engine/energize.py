"""課電判定（契約 §6.1 topology + §6.3 state → §6.4 energization）。

純粋なグラフ探索。LLM は使わない。

  - 閉じた開閉器と導体でつながる端子の連結成分を求める。
  - 成分に live な電源があれば live。無くて、閉じた接地開閉器があれば dead_grounded、無ければ dead_ungrounded。
  - live かつ接地あり → invalid（充電部に接地。逆送の見落としなど計画ミス）。errors にも書く。
  - 変圧器は巻線をまたいで両方向に伝播する。
  - state に書かれていないものは保守側に倒す: 開閉器は closed、接地開閉器は open、電源は live。

CLI:
  python -m engine.energize data/sites/SITE-01/truth/topology.json data/sites/SITE-01/truth/states/normal.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from engine.topology import SWITCH_KINDS, Topology

LIVE = "live"
DEAD_GROUNDED = "dead_grounded"
DEAD_UNGROUNDED = "dead_ungrounded"
INVALID = "invalid"


class _UnionFind:
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
class Component:
    nodes: list[str]
    edges: list[str]
    state: str
    live_sources: list[str] = field(default_factory=list)
    grounded_by: list[str] = field(default_factory=list)


@dataclass
class Energization:
    site_id: str
    step: int
    components: list[Component]
    errors: list[dict]
    _state_by_id: dict[str, str] = field(default_factory=dict, repr=False)
    _component_by_id: dict[str, int] = field(default_factory=dict, repr=False)

    # ---- 問い合わせ
    def state_of(self, ident: str) -> str:
        """ノードID・辺ID・端子ID（"CB-A.a"）の状態。開閉器 open のときノードIDで聞くと a 側を返す。"""
        if ident in self._state_by_id:
            return self._state_by_id[ident]
        if f"{ident}.a" in self._state_by_id:
            return self._state_by_id[f"{ident}.a"]
        if f"{ident}.hv" in self._state_by_id:
            return self._state_by_id[f"{ident}.hv"]
        raise KeyError(ident)

    def component_of(self, ident: str) -> Component:
        for key in (ident, f"{ident}.a", f"{ident}.hv"):
            if key in self._component_by_id:
                return self.components[self._component_by_id[key]]
        raise KeyError(ident)

    @property
    def invalid_ids(self) -> list[str]:
        return sorted(n for c in self.components if c.state == INVALID for n in c.nodes)

    def summary(self) -> dict:
        counts: dict[str, int] = defaultdict(int)
        for c in self.components:
            counts[c.state] += len(c.nodes)
        return {"nodes": dict(counts), "invalid": self.invalid_ids, "errors": len(self.errors)}

    def to_dict(self) -> dict:
        return {
            "schema_version": "0.1", "site_id": self.site_id, "step": self.step,
            "components": [
                {"nodes": c.nodes, "edges": c.edges, "state": c.state,
                 "live_sources": c.live_sources, "grounded_by": c.grounded_by}
                for c in self.components
            ],
            "errors": self.errors,
        }


def energize(topo: Topology, state: dict | None = None) -> Energization:
    st = state or {}
    switches: dict[str, str] = dict(st.get("switches", {}))
    sources: dict[str, str] = dict(st.get("sources", {}))
    errors: list[dict] = []

    for sid in switches:
        n = topo.nodes.get(sid)
        if n is None or n.kind not in SWITCH_KINDS + ("earthing",):
            errors.append({"code": "unknown_switch", "message": f"state.switches に無い機器 {sid}", "nodes": [sid]})
    for sid in sources:
        n = topo.nodes.get(sid)
        if n is None or n.kind != "source":
            errors.append({"code": "unknown_source", "message": f"state.sources に無い電源 {sid}", "nodes": [sid]})

    uf = _UnionFind(topo.terminal_ids())

    for e in topo.edges:
        uf.union(e.a, e.b)

    grounded_by: dict[str, list[str]] = defaultdict(list)
    closed_es: set[str] = set()
    for n in topo.nodes.values():
        if n.kind in SWITCH_KINDS:
            pos = switches.get(n.id, "closed")  # 保守側: 不明なら closed
            if pos == "closed":
                uf.union(f"{n.id}.a", f"{n.id}.b")
        elif n.kind == "transformer":
            uf.union(f"{n.id}.hv", f"{n.id}.lv")  # 両方向伝播
        elif n.kind == "earthing":
            pos = switches.get(n.id, "open")  # 保守側: 不明なら open
            if pos == "closed":
                term = topo.earthing_terminal(n)
                uf.union(term, n.id)
                closed_es.add(n.id)

    for es in closed_es:
        grounded_by[uf.find(es)].append(es)

    live_sources: dict[str, list[str]] = defaultdict(list)
    for n in topo.nodes.values():
        if n.kind == "source" and sources.get(n.id, "live") == "live":  # 保守側: 不明なら live
            live_sources[uf.find(n.id)].append(n.id)

    # ---- 成分ごとにまとめる
    members: dict[str, list[str]] = defaultdict(list)
    for t in topo.terminal_ids():
        n = topo.node_of(t)
        if n.kind == "earthing" and n.id not in closed_es:
            continue  # 開いている接地開閉器は成分に入れない（刃は大地側にあるだけ）
        members[uf.find(t)].append(t)
    edge_members: dict[str, list[str]] = defaultdict(list)
    for e in topo.edges:
        edge_members[uf.find(e.a)].append(e.id)

    components: list[Component] = []
    state_by_id: dict[str, str] = {}
    comp_by_id: dict[str, int] = {}
    for root in sorted(members, key=lambda r: min(members[r])):
        terms = members[root]
        is_live = root in live_sources
        is_g = root in grounded_by
        s = INVALID if (is_live and is_g) else LIVE if is_live else DEAD_GROUNDED if is_g else DEAD_UNGROUNDED
        # 端子を表示用のIDに畳む: 2端子ノードの両端子が同じ成分なら ノードID 一つ
        shown: list[str] = []
        by_node: dict[str, list[str]] = defaultdict(list)
        for t in terms:
            by_node[t.split(".", 1)[0]].append(t)
        for nid in sorted(by_node):
            n = topo.nodes[nid]
            if len(by_node[nid]) == len(n.terminals):
                shown.append(nid)
            else:
                shown.extend(sorted(by_node[nid]))
        comp = Component(shown, sorted(edge_members.get(root, [])), s,
                         sorted(live_sources.get(root, [])), sorted(grounded_by.get(root, [])))
        idx = len(components)
        components.append(comp)
        for ident in shown + comp.edges + terms:
            state_by_id[ident] = s
            comp_by_id[ident] = idx
        if s == INVALID:
            errors.append({"code": "live_grounded", "message": "充電している区間に接地が入っている（逆送の見落としか手順の誤り）",
                           "nodes": shown})

    return Energization(topo.site_id, int(st.get("step", 0)), components, errors, state_by_id, comp_by_id)


def live_edges(topo: Topology, res: Energization, exposed_only: bool = False,
               treat_ungrounded_as_live: bool = False) -> list:
    """充電している辺。exposed_only は離隔判定用（bare だけ）。
    treat_ungrounded_as_live=True は保守側の既定（§7.1）: 未接地の停止区間も課電扱いで返す。"""
    states = {LIVE, INVALID}
    if treat_ungrounded_as_live:
        states.add(DEAD_UNGROUNDED)
    return [e for e in topo.edges
            if res.state_of(e.id) in states and (not exposed_only or e.conductor == "bare")]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    topo = Topology.load(argv[1])
    state = json.loads(Path(argv[2]).read_text(encoding="utf-8")) if len(argv) > 2 else None
    res = energize(topo, state)
    print(json.dumps({"summary": res.summary(), "components": res.to_dict()["components"]}, ensure_ascii=False, indent=1))
    return 1 if res.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
