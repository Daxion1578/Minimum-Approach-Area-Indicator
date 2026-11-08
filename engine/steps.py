"""作業日の停止範囲（§7.6）。

取り替える機器（ノード）を選ぶと、その作業日に止める範囲を作る。開閉器操作の途中段階は扱わない
（クレーンが動くのは操作が終わった後。操作の順番は系統運用側の操作票の仕事）。

原則: 作業する機器に電気が流れ込む端すべてで電気を断つ。
  - 対象の端子ごとに、流入の道を外へたどる。最初に出会う断路器（目に見える切れ目）まで、途中の遮断器も含めて切る。
    例: 遮断器が対象 → 両隣の断路器。線路側断路器が対象 → 構内側は遮断器と母線側断路器。
  - 送電線（構外の電源）に出る道は、相手端の遮断器・断路器を切ることを「相手端の条件」に書き、その電源を停電として扱う。
  - 開閉器を挟まずに母線へ行き当たる端は、母線を止めず「端子の切り離し」を条件に書く（母線は充電のまま）。
  - 変圧器が対象のときは、変圧器専用のベイ（遮断器が 1 台だけのベイ）を母線の手前まで止める（遮断器と母線側断路器も切る）。
    ほかの回線と遮断器を共有するベイ（1・1/2 母線など）は、変圧器の隣の断路器で止め、共有の遮断器は平常どおり（11/6 本人）。
  - 切り離された作業対象以外は平常どおり運用する（最小の停止範囲）。
  - 接地は流入端すべてに作業手順で取る前提（線路側は ELS、その他はアース棒）。条件の先頭に書く。
状態は充電・停電の 2 形態で見る（停電＝全方向から切り離された区間）。判定はすべて決定論。Claude は関与しない。
"""
from __future__ import annotations

from collections import deque

from engine.energize import LIVE, INVALID, energize
from engine.topology import SWITCH_KINDS, Topology

TITLE = "作業日の停止範囲"
GROUNDING_NOTE = "作業する機器に電気が流れ込む端すべてに、検電してから接地を取る（線路側は ELS、その他はアース棒）"


def _adjacency(topo: Topology) -> dict[str, list[str]]:
    """端子 → 隣の端子。"""
    adj: dict[str, list[str]] = {}
    for e in topo.edges:
        adj.setdefault(e.a, []).append(e.b)
        adj.setdefault(e.b, []).append(e.a)
    return adj


def _other_terminal(term: str) -> str:
    nid, _, t = term.partition(".")
    return f"{nid}.{'b' if t == 'a' else 'a' if t == 'b' else 'lv' if t == 'hv' else 'hv'}"


def _label(topo: Topology, nid: str) -> str:
    n = topo.nodes[nid]
    num = _number(topo, nid)
    return f"{num} {n.name}".strip() if n.name else (num or nid)


def outage_scope(topo: Topology, targets: list[str]) -> dict:
    """対象から流入の道をたどり、切る遮断器・断路器、相手端の条件（停電にする電源）、端子の切り離しを集める。"""
    adj = _adjacency(topo)
    tset = set(targets)
    breakers: list[str] = []
    disconnectors: list[str] = []
    remote: list[str] = []          # 相手端を切る電源（source ノード）
    detach: list[tuple[str, str]] = []   # (母線, 手前の機器)
    detached_terms: set[str] = set()     # 端子の切り離しで断つ、対象の端子
    zone: set[str] = set()

    def note_open(nid: str):
        lst = breakers if topo.nodes[nid].kind == "breaker" else disconnectors
        if nid not in lst:
            lst.append(nid)

    breakers_in_bay: dict[str, int] = {}
    for n in topo.nodes.values():
        if n.kind == "breaker" and n.bay:
            breakers_in_bay[n.bay] = breakers_in_bay.get(n.bay, 0) + 1
    tr_targets = {t for t in targets if topo.nodes[t].kind == "transformer"}

    # (端子, 直前の機器ID, 出発した対象の端子)。変圧器の専用ベイをたどる間は lock にそのベイ名を持つ
    q: deque[tuple[str, str, str]] = deque()
    lock_of: dict[str, str] = {}
    for t in targets:
        n = topo.nodes[t]
        for term in n.terminals:
            tid = f"{t}.{term}" if term else t
            q.append((tid, t, tid))
    seen: set[str] = set()
    while q:
        term, prev, origin = q.popleft()
        if term in seen:
            continue
        seen.add(term)
        node = topo.node_of(term)
        if node.kind == "earthing":
            continue
        lock = lock_of.get(term)
        if lock:
            # 変圧器の専用ベイの中: 母線の手前まで、ベイの開閉器をすべて切る
            if node.kind == "bus" or node.bay != lock:
                continue
            if node.kind in SWITCH_KINDS:
                note_open(node.id)
            zone.add(term)
            o = _other_terminal(term) if node.kind in SWITCH_KINDS else None
            for t2 in ([o] if o else []) + ([] if o else adj.get(term, [])):
                if t2 not in seen:
                    lock_of[t2] = lock; q.append((t2, node.id, origin))
            if o:
                seen.add(o)
                for nxt in adj.get(o, []):
                    if nxt not in seen:
                        lock_of[nxt] = lock; q.append((nxt, node.id, origin))
            continue
        if node.id not in tset:
            if node.kind == "disconnector":
                note_open(node.id)       # 目に見える切れ目。ここで止まる
                if prev in tr_targets or (origin.split(".", 1)[0] in tr_targets):
                    if node.bay and breakers_in_bay.get(node.bay) == 1:
                        # 変圧器専用のベイ: この先の遮断器・母線側断路器まで切る
                        o = _other_terminal(term)
                        seen.add(o)
                        for nxt in adj.get(o, []):
                            lock_of[nxt] = node.bay; q.append((nxt, node.id, origin))
                continue
            if node.kind == "breaker":
                note_open(node.id)       # 遮断器は切って、その先の断路器まで進む
                o = _other_terminal(term)
                zone.update((term, o)); seen.add(o)
                for nxt in adj.get(o, []):
                    q.append((nxt, node.id, origin))
                continue
            if node.kind == "bus":
                if (node.id, prev) not in detach:
                    detach.append((node.id, prev))
                detached_terms.add(origin)
                continue
            if node.kind == "source":
                if node.id not in remote:
                    remote.append(node.id)
                zone.add(term)
                continue
        zone.add(term)
        if node.kind == "transformer" or (node.kind in SWITCH_KINDS and node.id in tset):
            # 変圧器・対象の開閉器はもう一方の端子へ（対象の端子なら、そちらが新しい出発点）
            o = _other_terminal(term)
            q.append((o, node.id, o if node.id in tset else origin))
        nxt_prev = node.id if node.kind not in ("terminal",) else prev
        for nxt in adj.get(term, []):
            q.append((nxt, nxt_prev, origin))
    return {"zone": sorted(zone), "breakers": breakers, "disconnectors": disconnectors,
            "remote_sources": remote, "detach": detach, "detached_terminals": sorted(detached_terms)}


def generate(topo: Topology, normal_state: dict, targets: list[str], note: str = "") -> dict:
    """作業日の停止範囲。targets はノードID（例 ["220-T2-CB"]）。normal_state は作業前の状態（追加停止なら今の状態）。

    返り値（steps.json）: ok, targets, ops（切る機器）, conditions（接地・相手端・端子の切り離し）, state（停止後）,
    steps（1 段。承認の書き出しと互換）, problems。
    """
    if not targets:
        # 対象なしで「通った」と返すと、何も止めていない計画が承認まで進みうる
        return {"ok": False, "targets": [], "steps": [], "ops": [], "conditions": [], "problems": ["対象が選ばれていない"]}
    for t in targets:
        if t not in topo.nodes:
            return {"ok": False, "targets": targets, "steps": [], "ops": [], "conditions": [], "problems": [f"unknown node {t}"]}
    sc = outage_scope(topo, targets)
    # 切る断路器が送電線（構外の電源）に直接つながっていれば、送電線ごと止める（相手端も切る）。
    # 線路の機器を取り替えるとき、線路断路器の外側（引留鉄構からの下り線）が充電のまま残るとベイの中で吊れないため（本人の判断 2026-11-08）
    cut = set(sc["disconnectors"]) | {t for t in targets if topo.nodes[t].kind == "disconnector"}
    for e in topo.edges:
        for here, there in ((e.a, e.b), (e.b, e.a)):
            if here.split(".", 1)[0] in cut:
                n = topo.node_of(there)
                if n.kind == "source" and n.id not in sc["remote_sources"]:
                    sc["remote_sources"].append(n.id)
    base_sw = dict(normal_state.get("switches", {}))
    base_src = dict(normal_state.get("sources", {}))

    def op(sid: str) -> dict:
        n = topo.nodes[sid]
        return {"id": sid, "to": "open", "number": _number(topo, sid), "name": n.name or sid, "kind": n.kind}

    # 対象が開閉器ならそれ自身も切る（取り替える機器）。元から開いている開閉器は操作しない（差分だけ）
    own = [t for t in targets if topo.nodes[t].kind in SWITCH_KINDS]
    to_open = list(dict.fromkeys(sorted(own, key=lambda x: topo.nodes[x].kind != "breaker") + sc["breakers"] + sc["disconnectors"]))
    ops = [op(s) for s in to_open if base_sw.get(s, "closed") != "open"]
    sw = dict(base_sw)
    for s in to_open:
        sw[s] = "open"
    src = dict(base_src)
    for s in sc["remote_sources"]:
        src[s] = "dead"
    conditions = [GROUNDING_NOTE]
    conditions += [f"相手端（{_label(topo, s)}）の遮断器・断路器を切る（相手端の条件。こちらでは操作しない）" for s in sc["remote_sources"]]
    conditions += [f"{_label(topo, b)} は止めないので、{_label(topo, p)} の母線側の端子を物理的に切り離す（母線は充電のまま）"
                   for b, p in sc["detach"]]
    state = {"schema_version": "0.1", "site_id": topo.site_id, "step": 1,
             "note": note or f"作業日の停止範囲（対象 {', '.join(targets)}）", "sources": src, "switches": sw}
    res = energize(topo, state)
    # 対象の端子がすべて停電になること。端子の切り離しで断つ端子は、切り離すまで充電のまま（保守側にそのまま充電で扱う）
    problems = []
    for t in targets:
        for term in topo.nodes[t].terminals:
            tid = f"{t}.{term}" if term else t
            if tid in sc["detached_terminals"]:
                continue
            try:
                st = res.state_of(tid)
            except KeyError:
                problems.append(f"{t} の状態が取れない")
                continue
            if st in (LIVE, INVALID):
                problems.append(f"{_label(topo, t)} が停電にならない（流入の道が残っている）")
    problems += [e["message"] for e in res.errors]
    problems = list(dict.fromkeys(problems))
    step = {"n": 1, "title": TITLE, "ops": ops, "state": state, "summary": res.summary(), "conditions": conditions}
    return {"schema_version": "0.1", "site_id": topo.site_id, "ok": not problems, "targets": targets,
            "zone": sc["zone"], "ops": ops, "conditions": conditions, "state": state,
            "steps": [step], "problems": problems}


def _number(topo: Topology, sid: str) -> str:
    for nd in topo.raw.get("nodes", []):
        if nd["id"] == sid:
            return nd.get("number", "")
    return ""
