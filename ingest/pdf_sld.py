"""単線結線図（ベクター PDF）の取込（§8）。線と文字から「候補グラフ」を作り、§6.1 の topology の下書きにする。

やること（決定論の部分）:
  1. 文字を拾う。開閉器番号（例 20E1-110、6T-2103E）、母線名、線路名、変圧器（1BK）、調相（#1SC）
  2. 主回路の線分（線幅で区別。母線はさらに太い）を拾い、端点をつないで「ネット」（電気的に一続きの導体）にする。
     開閉器の記号の位置では線をつながない（記号が線を切る）
  3. 開閉器を、記号の位置に接する 2 つのネットの間に置く。接地開閉器は付いているネットに置く
  4. 線路名のそばで終わるネットは線路（電源）、変圧器のそばで終わるネットは変圧器の一次／二次
  5. 結果を候補グラフ（candidate.json）にし、§6.1 topology の下書きに変換する。迷った点は questions に残す
Claude の役割（agent/structure.py）: 候補グラフの意味づけ（記号の種別・名前の補完）と質問文。接続そのものはここで決める。
対象は、ベクター PDF の文字が取り出せる図面。スキャン画像は対象外。
"""
from __future__ import annotations

import io
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber

PT = 72 / 25.4           # 1mm = PT pt
NUM_RE = re.compile(r"^(?:20|6)[A-Z0-9]{1,4}-\d{1,4}E?$")
TR_RE = re.compile(r"^\dBK$")
LOAD_RE = re.compile(r"^#\d(SC|SR)$")
LINE_RE = re.compile(r"^[^\s（）]+線\dL（[^）]+）$")
BUS_RE = re.compile(r"^(220|66)kV\s*(母線|\d号母線)")


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_on_segment(p, a, b, tol):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return _dist(p, a) < tol
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    if t < 0.02 or t > 0.98:        # 端点どうしはスナップで扱う。ここは途中だけ
        return False
    cx, cy = ax + t * dx, ay + t * dy
    return _dist(p, (cx, cy)) < tol


def extract(pdf_path: str | Path, main_width: float = 0.85, bus_width: float = 1.4, min_len: float = 5.0) -> dict:
    """PDF 1 ページから候補グラフを作る。座標は mm（左下原点）。"""
    # バイト列から開く。ファイルを掴んだままにしない（Windows では掴んだままだと消せない）
    pdf = pdfplumber.open(io.BytesIO(Path(pdf_path).read_bytes()))
    pg = pdf.pages[0]
    H = pg.height

    # ---- 文字（単語）----
    words = []
    for w in pg.extract_words(keep_blank_chars=False):
        x0, x1 = w["x0"] / PT, w["x1"] / PT
        yb = (H - w["bottom"]) / PT + 0.3   # ベースライン（下端から少し上）
        words.append({"text": w["text"], "x0": x0, "x1": x1, "y": yb})
    switches, trs, loads, lines, buses = [], [], [], [], []
    for w in words:
        t = w["text"]
        if NUM_RE.match(t):
            if t.endswith("E"):
                # 接地開閉器の番号は記号の左（右寄せ）。番号の右 4.5mm・下 1mm に記号、付く導体はさらにその右（6mm 以内）
                # 回路側（線路・変圧器・調相）の接地は記号の右下に番号。その場合は番号の左 6.5mm・上 6mm に導体がある
                switches.append({"number": t, "x": w["x1"] + 4.2, "y": w["y"] - 1.0, "kind_guess": "earthing", "label_x": w["x0"], "label_x1": w["x1"], "label_y": w["y"]})
            else:
                switches.append({"number": t, "x": w["x0"] - 2.6, "y": w["y"] + 0.8, "kind_guess": kind_from_number(t), "label_x": w["x0"], "label_y": w["y"]})
        elif TR_RE.match(t):
            trs.append({"number": t, "x": w["x0"] - 4.0, "y": w["y"] - 1.0})      # 記号（2 重丸）は番号の左
        elif LOAD_RE.match(t):
            loads.append({"name": t, "x": w["x0"] - 3.5, "y": w["y"]})
        elif LINE_RE.match(t):
            lines.append({"name": t.split("（")[0], "label": t, "x": w["x0"] - 1.5, "y": w["y"]})
        elif BUS_RE.match(t):
            buses.append({"name": t, "x": w["x0"], "y": w["y"]})
    # 「66kV 1号母線」のように 2 語に割れた場合をつなぐ
    for i, w in enumerate(words):
        if w["text"] in ("220kV", "66kV") and i + 1 < len(words) and "母線" in words[i + 1]["text"] and abs(words[i + 1]["y"] - w["y"]) < 1.0:
            buses.append({"name": w["text"] + " " + words[i + 1]["text"], "x": w["x0"], "y": w["y"]})

    # ---- 主回路の線分 ----
    segs = []
    aux = []
    for ln in pg.lines:
        lw = ln.get("linewidth") or 0
        if lw < main_width:
            if lw >= 0.3:
                (xa, ya), (xb, yb) = ln["pts"][0], ln["pts"][1]
                aux.append(((xa / PT, (H - ya) / PT), (xb / PT, (H - yb) / PT)))
            continue
        dash = ln.get("dash")
        if dash and dash[0]:
            continue      # 破線は計画・予定（新設ベイなど）。導体としては扱わない
        (xa, ya), (xb, yb) = ln["pts"][0], ln["pts"][1]
        a, b = (xa / PT, (H - ya) / PT), (xb / PT, (H - yb) / PT)
        axis = abs(a[0] - b[0]) < 0.2 or abs(a[1] - b[1]) < 0.2
        if _dist(a, b) < (3.0 if axis else min_len):
            continue      # 記号の線（ブレード・×・矢印は斜めで短い、横棒は 2.4mm）を除き、導体の線分だけ残す
        segs.append({"a": a, "b": b, "w": lw, "bus": lw >= bus_width})
    # pdfplumber の pts は上原点なので y を反転済み（H - y）

    # ---- ネット: 端点をつなぐ。開閉器の記号の近く（1.8mm）では切る ----
    sw_pts = [(s["x"], s["y"]) for s in switches if s["kind_guess"] != "earthing"]
    tr_pts = [(t["x"], t["y"]) for t in trs]

    def key_of(p, i, end):
        for q in sw_pts:
            if _dist(p, q) < 1.8:
                return f"sw{i}{end}"         # 記号で切る（固有キー）
        for q in tr_pts:
            if _dist(p, q) < 6.0:
                return f"tr{i}{end}"         # 変圧器の記号でも切る
        return (round(p[0] / 0.6), round(p[1] / 0.6))   # 0.6mm 格子でスナップ

    uf = _UF()
    for i, s in enumerate(segs):
        ka, kb = key_of(s["a"], i, "a"), key_of(s["b"], i, "b")
        uf.union(f"seg{i}", ka); uf.union(f"seg{i}", kb)
    # T 字の分岐: 端点が別の線分の途中に乗っていればつなぐ（図面の「・」接続点に相当。開閉器の記号の近くは除く）
    for i, s in enumerate(segs):
        for end in ("a", "b"):
            p = s[end]
            if any(_dist(p, q) < 1.8 for q in sw_pts):
                continue
            for j, t in enumerate(segs):
                if i == j:
                    continue
                if _point_on_segment(p, t["a"], t["b"], 0.6):
                    uf.union(f"seg{i}", f"seg{j}")
    net_of_seg = {i: uf.find(f"seg{i}") for i in range(len(segs))}
    nets: dict = {}
    for i, s in enumerate(segs):
        n = nets.setdefault(net_of_seg[i], {"segs": [], "bus": False, "pts": []})
        n["segs"].append(i); n["bus"] = n["bus"] or s["bus"]; n["pts"] += [s["a"], s["b"]]
    net_ids = {root: f"N{k + 1}" for k, root in enumerate(sorted(nets, key=lambda r: min(nets[r]["segs"])))}

    def seg_dist(p, s):
        ax, ay = s["a"]; bx, by = s["b"]; dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
        return _dist(p, (ax + t * dx, ay + t * dy))

    def nets_near(p, tol):
        """点に近いネット（線分までの距離で測る。端点だけでは隣の区間と区別できない）。"""
        found = []
        for root, n in nets.items():
            d = min(seg_dist(p, segs[i]) for i in n["segs"])
            if d < tol:
                found.append((d, net_ids[root]))
        return [nid for _, nid in sorted(found)]

    # ---- 開閉器 → ネット ----
    for s in switches:
        if s["kind_guess"] == "earthing":
            # 接地は補助線（細線）の枝で主回路につながる。枝の一端は主回路の上（≤1mm）、他端は番号のすぐ脇
            # （番号の左 2.5mm か右 1.5mm で 1mm 下、または番号の左 2.5mm で 3.5mm 上）。その枝が乗っている主回路のネットを取る
            anchors = [(s["label_x"] - 2.5, s["label_y"] - 1.0), (s["label_x1"] + 1.5, s["label_y"] - 1.0), (s["label_x"] - 2.5, s["label_y"] + 3.5)]
            best = None
            for a, b in aux:
                for p_, q_ in ((a, b), (b, a)):
                    da = min(_dist(q_, an) for an in anchors)
                    if da > 3.0:
                        continue
                    for nid in nets_near(p_, 1.0)[:1]:
                        if best is None or da < best[0]:
                            best = (da, nid)
            s["nets"] = [best[1]] if best else nets_near((s["x"], s["y"]), 4.0)[:1]
        else:
            cands = nets_near((s["x"], s["y"]), 4.5)
            s["nets"] = cands[:2]
    # ---- ネットの意味づけ ----
    net_info = {}
    for root, n in nets.items():
        nid = net_ids[root]
        info = {"id": nid, "kind": "bus" if n["bus"] else "conductor", "name": None, "n_segments": len(n["segs"])}
        if n["bus"]:
            # 近い母線ラベル
            best = None
            for b in buses:
                d = min(abs(b["y"] - q[1]) for q in n["pts"]) + 0.02 * min(abs(b["x"] - q[0]) for q in n["pts"])
                if best is None or d < best[0]:
                    best = (d, b["name"])
            info["name"] = best[1] if best else None
        net_info[nid] = info
    for ln in lines:
        for nid in nets_near((ln["x"], ln["y"]), 8.0)[:1]:
            net_info[nid]["kind"] = "line"; net_info[nid]["name"] = ln["name"]
    for ld in loads:
        for nid in nets_near((ld["x"], ld["y"] - 4.0), 8.0)[:1]:
            net_info[nid]["kind"] = "load"; net_info[nid]["name"] = ld["name"]
    for tr in trs:
        above = nets_near((tr["x"], tr["y"] + 6.0), 4.0)
        below = nets_near((tr["x"], tr["y"] - 6.0), 4.0)
        tr["hv_net"] = above[0] if above else None
        tr["lv_net"] = below[0] if below else None

    questions = []
    for s in switches:
        need = 1 if s["kind_guess"] == "earthing" else 2
        if len(s["nets"]) < need:
            questions.append({"about": s["number"], "q": f"{s['number']} の記号に接する導体が {len(s['nets'])} 本しか見つからない（{need} 本のはず）。図面の記号の位置を確かめてほしい"})
    for tr in trs:
        if not tr["hv_net"] or not tr["lv_net"]:
            questions.append({"about": tr["number"], "q": f"{tr['number']} の一次／二次につながる導体が見つからない"})
    return {
        "source": str(pdf_path), "unit": "mm", "page_size_mm": [pg.width / PT, pg.height / PT],
        "nets": list(net_info.values()),
        "switches": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()} for s in switches],
        "transformers": trs, "loads": loads, "lines": lines, "buses": buses,
        "questions": questions,
        "stats": {"words": len(words), "main_segments": len(segs), "nets": len(nets)},
    }


def kind_from_number(num: str) -> str:
    """開閉器番号の規則（合成）: 末尾 E=接地、ハイフンの後が 3 桁で末尾 0=遮断器、それ以外=断路器。"""
    if num.endswith("E"):
        return "earthing"
    tail = num.split("-")[-1]
    return "breaker" if len(tail) == 3 and tail.endswith("0") else "disconnector"


def to_topology(cand: dict, site_id: str = "IMPORTED", name: str = "図面取込（未確認）") -> dict:
    """候補グラフ → §6.1 topology の下書き。ネットは bus / source / load / terminal のノードに、開閉器は 2 端子ノードに。"""
    nodes, edges = [], []
    kv_of = lambda num: 220 if num.startswith("20") else 66
    net_kv: dict[str, int] = {}
    for s in cand["switches"]:
        for n in s.get("nets", []):
            net_kv.setdefault(n, kv_of(s["number"]))
    for n in cand["nets"]:
        kv = net_kv.get(n["id"], 66)
        kind = {"bus": "bus", "line": "source", "load": "load"}.get(n["kind"], "terminal")
        nd = {"id": n["id"], "kind": kind, "voltage_kv": kv}
        if n.get("name"):
            nd["name"] = n["name"]
        nodes.append(nd)
    for s in cand["switches"]:
        k = s["kind_guess"]; kv = kv_of(s["number"])
        sid = "SW-" + s["number"]
        if k == "earthing":
            if s.get("nets"):
                nodes.append({"id": sid, "kind": "earthing", "voltage_kv": kv, "number": s["number"], "attached_to": s["nets"][0]})
            continue
        nodes.append({"id": sid, "kind": k, "voltage_kv": kv, "number": s["number"]})
        ns = s.get("nets", [])
        if len(ns) >= 1:
            edges.append({"id": f"{sid}-a", "from": ns[0], "to": f"{sid}.a", "conductor": "bare"})
        if len(ns) >= 2:
            edges.append({"id": f"{sid}-b", "from": f"{sid}.b", "to": ns[1], "conductor": "bare"})
    for tr in cand["transformers"]:
        tid = "TR-" + tr["number"]
        nodes.append({"id": tid, "kind": "transformer", "number": tr["number"], "windings": {"hv": {"voltage_kv": 220}, "lv": {"voltage_kv": 66}}})
        if tr.get("hv_net"):
            edges.append({"id": f"{tid}-hv", "from": tr["hv_net"], "to": f"{tid}.hv", "conductor": "enclosed"})
        if tr.get("lv_net"):
            edges.append({"id": f"{tid}-lv", "from": f"{tid}.lv", "to": tr["lv_net"], "conductor": "enclosed"})
    return {"schema_version": "0.1", "site_id": site_id, "generated_by": "ingest/pdf_sld.py", "name": name,
            "notes": ["図面取込の下書き。人が確認するまで『未確認』。"], "nodes": nodes, "edges": edges,
            "questions": [q["q"] for q in cand.get("questions", [])]}


def main(argv):
    out = extract(argv[1])
    print(json.dumps({k: out[k] for k in ("stats", "questions")}, ensure_ascii=False, indent=1))
    if len(argv) > 2:
        Path(argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    import sys
    main(sys.argv)
