"""停止ステップの自動生成（§7.6）。

取り替える機器（ノード）を選ぶと、実務の隔離手順の形で段階を作る:
  1. 対象を囲む遮断器を開放（遮断器で電流を切ってから断路器を開ける）
  2. 対象と遮断器の間、および遮断器の反対側（母線側）の断路器を開放（二重の隔離）
  3. 停電した区間の接地開閉器を投入
各段階の状態（state.json）を作り、課電判定で確かめる（対象が dead_grounded になり、live_grounded の誤りが無いこと）。
判定はすべて決定論。Claude はここに関与しない。
"""
from __future__ import annotations

from collections import deque

from engine.energize import DEAD_GROUNDED, DEAD_UNGROUNDED, energize
from engine.topology import SWITCH_KINDS, Topology

TITLES = {1: "遮断器を開放", 2: "断路器を開放（両側）", 3: "接地開閉器を投入"}


def _adjacency(topo: Topology) -> dict[str, list[tuple[str, str]]]:
    """端子 → [(相手端子, 辺ID)]。"""
    adj: dict[str, list[tuple[str, str]]] = {}
    for e in topo.edges:
        adj.setdefault(e.a, []).append((e.b, e.id))
        adj.setdefault(e.b, []).append((e.a, e.id))
    return adj


def _other_terminal(term: str) -> str:
    nid, _, t = term.partition(".")
    return f"{nid}.{'b' if t == 'a' else 'a' if t == 'b' else 'lv' if t == 'hv' else 'hv'}"


def isolation_boundary(topo: Topology, targets: list[str]) -> dict:
    """対象から外へ向かって、最初に出会う開閉器と、遮断器の向こう側の断路器を集める。"""
    adj = _adjacency(topo)
    zone: set[str] = set()          # 対象の区域（端子）
    boundary: list[tuple[str, str]] = []   # (開閉器ID, 触れた端子)
    tset = set(targets)
    q: deque[str] = deque()
    for t in targets:
        n = topo.nodes[t]
        for term in n.terminals:
            q.append(f"{t}.{term}" if term else t)
    while q:
        term = q.popleft()
        if term in zone:
            continue
        node = topo.node_of(term)
        if node.kind in SWITCH_KINDS and node.id not in tset:
            boundary.append((node.id, term))
            continue
        zone.add(term)
        if node.kind == "transformer" or (node.kind in SWITCH_KINDS and node.id in tset):
            q.append(_other_terminal(term))     # 対象の開閉器は両側を区域に入れる（機器そのものの取替）
        for nxt, _ in adj.get(term, []):
            q.append(nxt)

    breakers: list[str] = [t for t in targets if topo.nodes[t].kind == "breaker"]          # 対象が開閉器ならそれ自身も開ける
    disconnectors: list[str] = [t for t in targets if topo.nodes[t].kind == "disconnector"]

    def walk_out(from_term: str, past_cb: bool = False):
        """開閉器の反対側の端子から外へ歩く。遮断器に出会うまで断路器を集め、遮断器の向こうの断路器 1 段で止まる。"""
        seen: set[str] = set()
        q2: deque[tuple[str, bool]] = deque([(nxt, past_cb) for nxt, _ in adj.get(from_term, [])])
        while q2:
            term, past = q2.popleft()
            if term in seen or term in zone:
                continue
            seen.add(term)
            node = topo.node_of(term)
            if node.kind == "breaker":
                if node.id not in breakers:
                    breakers.append(node.id)
                for nxt, _ in adj.get(_other_terminal(term), []):
                    q2.append((nxt, True))
                continue
            if node.kind == "disconnector":
                if node.id not in disconnectors:
                    disconnectors.append(node.id)
                if past:
                    continue          # 遮断器の向こうの断路器で止まる
                for nxt, _ in adj.get(_other_terminal(term), []):
                    q2.append((nxt, past))
                continue
            if node.kind in ("bus", "source"):
                continue              # 母線・電源に出たら止まる
            if node.kind == "transformer":
                q2.append((_other_terminal(term), past))
            for nxt, _ in adj.get(term, []):
                q2.append((nxt, past))

    for sid, term in boundary:
        node = topo.nodes[sid]
        if node.kind == "breaker":
            if sid not in breakers:
                breakers.append(sid)
            walk_out(_other_terminal(term), past_cb=True)
        else:
            if sid not in disconnectors:
                disconnectors.append(sid)
            walk_out(_other_terminal(term))
    return {"zone": sorted(zone), "breakers": breakers, "disconnectors": disconnectors}


def generate(topo: Topology, normal_state: dict, targets: list[str], note: str = "") -> dict:
    """§6.8 steps.json。targets はノードID（例 ["TR-2"]）。"""
    for t in targets:
        if t not in topo.nodes:
            return {"ok": False, "targets": targets, "steps": [], "problems": [f"unknown node {t}"]}
    b = isolation_boundary(topo, targets)
    base = {"schema_version": "0.1", "site_id": topo.site_id, "step": 0, "note": note or f"対象 {', '.join(targets)} の停止",
            "sources": dict(normal_state.get("sources", {})), "switches": dict(normal_state.get("switches", {}))}

    def op(sid: str, to: str) -> dict:
        n = topo.nodes[sid]
        return {"id": sid, "to": to, "number": topo.raw_number(sid) if hasattr(topo, "raw_number") else _number(topo, sid), "name": n.name or sid, "kind": n.kind}

    steps = []
    sw = dict(base["switches"])
    # 1 遮断器
    ops1 = [op(s, "open") for s in b["breakers"]]
    for o in ops1:
        sw[o["id"]] = "open"
    s1 = {**base, "step": 1, "switches": dict(sw)}
    r1 = energize(topo, s1)
    steps.append({"n": 1, "title": TITLES[1], "ops": ops1, "state": s1, "summary": r1.summary()})
    # 2 断路器
    ops2 = [op(s, "open") for s in b["disconnectors"]]
    for o in ops2:
        sw[o["id"]] = "open"
    s2 = {**base, "step": 2, "switches": dict(sw)}
    r2 = energize(topo, s2)
    steps.append({"n": 2, "title": TITLES[2], "ops": ops2, "state": s2, "summary": r2.summary()})
    # 3 接地: 段階 2 で新たに停電（未接地）になった端子に付く接地開閉器（もともと停電の新設区間は除く）
    r0 = energize(topo, base)
    ops3 = []
    for n in topo.nodes.values():
        if n.kind != "earthing":
            continue
        term = topo.earthing_terminal(n)
        try:
            st = r2.state_of(term); st0 = r0.state_of(term)
        except KeyError:
            continue
        if st == DEAD_UNGROUNDED and st0 != DEAD_UNGROUNDED:
            ops3.append(op(n.id, "closed"))
    for o in ops3:
        sw[o["id"]] = "closed"
    s3 = {**base, "step": 3, "switches": dict(sw)}
    r3 = energize(topo, s3)
    steps.append({"n": 3, "title": TITLES[3], "ops": ops3, "state": s3, "summary": r3.summary()})

    problems = []
    for t in targets:
        try:
            if r3.state_of(t) != DEAD_GROUNDED:
                problems.append(f"{t} が接地済みの停電になっていない（{r3.state_of(t)}）")
        except KeyError:
            problems.append(f"{t} の状態が取れない")
    problems += [e["message"] for e in r3.errors]
    return {"schema_version": "0.1", "site_id": topo.site_id, "ok": not problems, "targets": targets,
            "zone": b["zone"], "steps": steps, "problems": problems}


def _number(topo: Topology, sid: str) -> str:
    for nd in topo.raw.get("nodes", []):
        if nd["id"] == sid:
            return nd.get("number", "")
    return ""
