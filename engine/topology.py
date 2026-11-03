"""topology.json（契約 §6.1）の読み込みと端子の解決。

端子（terminal）の約束:
  - breaker / disconnector は端子 a・b を持つ。参照は "CB-A.a" のように書く。
  - transformer は端子 hv・lv を持つ。
  - それ以外（source / bus / terminal / load / earthing）は端子が一つで、ノードIDだけで参照する。
  - 開閉器を端子名なしで参照した辺は、辺の並び順で 1本目が a、2本目が b。3本目はエラー。
  - earthing ノードの attached_to も同じ規則で解決する（開閉器を指すときは端子名を書く）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SWITCH_KINDS = ("breaker", "disconnector")
TWO_TERMINAL = {"breaker": ("a", "b"), "disconnector": ("a", "b"), "transformer": ("hv", "lv")}


class TopologyError(ValueError):
    pass


@dataclass
class Node:
    id: str
    kind: str
    voltage_kv: float | None = None
    windings: dict | None = None
    attached_to: str | None = None
    name: str | None = None
    bay: str | None = None

    @property
    def terminals(self) -> tuple[str, ...]:
        return TWO_TERMINAL.get(self.kind, ("",))


@dataclass
class Edge:
    id: str
    a: str  # 解決済み端子 "NODE" または "NODE.x"
    b: str
    conductor: str
    name: str | None = None


@dataclass
class Topology:
    site_id: str
    nodes: dict[str, Node]
    edges: list[Edge]
    raw: dict = field(repr=False)

    def terminal_ids(self) -> list[str]:
        out: list[str] = []
        for n in self.nodes.values():
            for t in n.terminals:
                out.append(f"{n.id}.{t}" if t else n.id)
        return out

    def node_of(self, terminal: str) -> Node:
        return self.nodes[terminal.split(".", 1)[0]]

    def earthing_terminal(self, es: Node) -> str:
        assert es.kind == "earthing" and es.attached_to
        return self._resolve(es.attached_to, allow_bare_switch=False, context=f"earthing {es.id}")

    # ------------------------------------------------------------------ 読み込み
    @classmethod
    def from_dict(cls, d: dict) -> "Topology":
        nodes: dict[str, Node] = {}
        for nd in d["nodes"]:
            if nd["id"] in nodes:
                raise TopologyError(f"duplicate node id {nd['id']}")
            nodes[nd["id"]] = Node(
                id=nd["id"], kind=nd["kind"], voltage_kv=nd.get("voltage_kv"), windings=nd.get("windings"),
                attached_to=nd.get("attached_to"), name=nd.get("name"), bay=nd.get("bay"),
            )
        topo = cls(site_id=d["site_id"], nodes=nodes, edges=[], raw=d)
        used: dict[str, int] = {}  # switch id -> number of bare references assigned
        seen_edge_ids: set[str] = set()
        for ed in d["edges"]:
            a = topo._resolve(ed["from"], True, f"edge {ed.get('id', '?')}", used)
            b = topo._resolve(ed["to"], True, f"edge {ed.get('id', '?')}", used)
            eid = ed.get("id") or f"{ed['from']}--{ed['to']}"
            if eid in seen_edge_ids:
                raise TopologyError(f"duplicate edge id {eid}")
            seen_edge_ids.add(eid)
            topo.edges.append(Edge(eid, a, b, ed["conductor"], ed.get("name")))
        for n in nodes.values():
            if n.kind == "earthing":
                topo.earthing_terminal(n)  # 解決できることを確かめる
        return topo

    @classmethod
    def load(cls, path: str | Path) -> "Topology":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def _resolve(self, ref: str, allow_bare_switch: bool, context: str, used: dict[str, int] | None = None) -> str:
        nid, _, term = ref.partition(".")
        node = self.nodes.get(nid)
        if node is None:
            raise TopologyError(f"{context}: unknown node {nid!r}")
        terms = node.terminals
        if term:
            if term not in terms:
                raise TopologyError(f"{context}: node {nid} has no terminal {term!r} (has {terms})")
            return f"{nid}.{term}"
        if terms == ("",):
            return nid
        if not allow_bare_switch or used is None:
            raise TopologyError(f"{context}: {nid} needs a terminal name ({'/'.join(terms)})")
        k = used.get(nid, 0)
        if k >= len(terms):
            raise TopologyError(f"{context}: {nid} referenced without terminal more than {len(terms)} times")
        used[nid] = k + 1
        return f"{nid}.{terms[k]}"
