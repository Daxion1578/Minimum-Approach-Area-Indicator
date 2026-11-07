"""機械器具装置図（平面 1/400 ＋ 断面 A-A・B-B・C-C が 1 枚の PDF）から、機器の位置と高さを読む。決定論。Claude は呼ばない。

読むもの（図面の約束は synth/drawing_rules.py。生成側と同じ規則を import して逆に解く）:
  - 平面の機器番号の文字 → center_from_text で機器の中心 (x, y)（m）
  - 平面の母線の太線（線幅で電圧階級を判別）→ 母線の y と x の範囲
  - 平面の "LA"（避雷器）の文字 → 避雷器の位置
  - 断面の高さラベル "<要素> GL+<mm>" → 要素の高さ。ラベルの紙 x から要素の y も戻す（引留鉄構・鉄塔・母線の y）

読めなかった・重なって曖昧・規則に合わないものは questions に文字列で出す（人が確かめる）。
結線図（topology）は任意。与えると 番号→id の対応と kind が埋まる。無いときは番号の形から kind を推定する（推定した旨を questions に出す）。

使い方:
    from ingest.pdf_layout import extract_layout
    ex = extract_layout("data/sites/SITE-01/drawings/SITE-01_layout.pdf", topology=topo)
"""
from __future__ import annotations

import re

import pdfplumber

from synth import drawing_rules as dr

MM = 72 / 25.4

# 高さラベルは要素の紙 x の右 1.2 mm に置かれる（gen_drawings.height_labels と同じ。drawing_rules にはまだ無い約束）
HEIGHT_LABEL_DX_MM = 1.2
# 平面の構内範囲（m）。これを外れた中心は「規則に合わない」とみなす
SITE_BOX_M = (-2.0, -2.0, 140.0, 130.0)

# 機器番号らしい文字（topology が無いときの候補拾い）
NUMBER_RE = re.compile(r"^(?:\d{1,2}[A-Z]\w*-\d+E?|\d+BK|#\d+(?:SC|SR))$")
BUS_LABEL_RE = re.compile(r"^(\d+)kV (\d+)号母線$")


# --------------------------------------------------------------------------
# 文字・線の取り出し
# --------------------------------------------------------------------------
def _words(page) -> list[dict]:
    """文字を baseline ごとにつなぎ、{text, x, y}（左下の紙 mm）の列にする。回転した文字は除く。"""
    chars = [c for c in page.chars if abs(c["matrix"][1]) < 1e-6 and abs(c["matrix"][2]) < 1e-6]
    chars.sort(key=lambda c: (round(c["matrix"][5], 1), c["matrix"][4]))
    out, cur = [], None
    for c in chars:
        e, f = c["matrix"][4], c["matrix"][5]
        if cur and abs(f - cur["f"]) < 0.05 and -0.3 < e - cur["end"] < 0.6:
            cur["text"] += c["text"]
        else:
            if cur:
                out.append(cur)
            cur = {"text": c["text"], "e": e, "f": f}
        cur["end"] = c["x1"]
    if cur:
        out.append(cur)
    return [{"text": w["text"].strip(), "x": w["e"] / MM, "y": w["f"] / MM} for w in out if w["text"].strip()]


def _hlines(page, x_max_mm: float, width_pt: float, tol: float = 0.01) -> list[tuple[float, float, float]]:
    """平面（紙 x が x_max_mm 未満）にある水平線のうち、線幅が width_pt のもの → (y_mm, x0_mm, x1_mm)。"""
    res = []
    for ln in page.lines:
        if abs(ln["linewidth"] - width_pt) > tol:
            continue
        if abs(ln["y0"] - ln["y1"]) > 1e-3:
            continue
        x0, x1 = sorted((ln["x0"] / MM, ln["x1"] / MM))
        if x1 < x_max_mm:
            res.append((ln["y0"] / MM, x0, x1))
    return res


def _group(vals: list[float], gap: float) -> list[list[float]]:
    vals = sorted(vals)
    groups: list[list[float]] = []
    for v in vals:
        if groups and v - groups[-1][-1] <= gap:
            groups[-1].append(v)
        else:
            groups.append([v])
    return groups


# --------------------------------------------------------------------------
# 番号の分類（topology が無いとき）
# --------------------------------------------------------------------------
def _guess_symbol(text: str) -> dict | None:
    """機器番号の形から記号の種類・軸を推定する。例: "6T-110" → cb_66、"20E1-1101" → ds_panto_220。推定できなければ None。"""
    if re.fullmatch(r"\d+BK", text):
        return {"kind": "transformer", "along": "y", "node_kind": "transformer", "kv": None}
    m = re.fullmatch(r"#\d+(SC|SR)", text)
    if m:
        return {"kind": f"load_{m.group(1)}", "along": "y", "node_kind": "load", "kv": 66}
    if not NUMBER_RE.match(text):
        return None
    kv = 220 if text.startswith("20") else 66
    if text.endswith("E"):
        return {"kind": "earthing", "along": "y", "node_kind": "earthing", "kv": kv}
    suffix = text.split("-")[-1]
    if len(suffix) == 3 and suffix.endswith(("10", "20", "30")):
        return {"kind": f"cb_{kv}", "along": "y", "node_kind": "breaker", "kv": kv}
    if kv == 220 and text.startswith("20B-"):                       # 母線上のセクション断路器
        return {"kind": "ds_220", "along": "x", "node_kind": "disconnector", "kv": kv}
    if kv == 220 and len(suffix) == 4 and suffix.endswith("101"):   # パンタ型（母線側断路器）
        return {"kind": "ds_panto_220", "along": "y", "node_kind": "disconnector", "kv": kv}
    return {"kind": f"ds_{kv}", "along": "y", "node_kind": "disconnector", "kv": kv}


def _symbol_from_topology(node: dict) -> dict:
    kv = node.get("voltage_kv")
    kind = dr.symbol_kind(node["kind"], kv or 220, node["id"])
    return {"kind": kind, "along": dr.orientation(node["id"])["along"], "node_kind": node["kind"], "kv": kv}


def _label_of(node: dict) -> str:
    """図面に書かれる文字: 番号。調相設備は番号が無いので名前。"""
    return node.get("number") or node.get("name", "")


# --------------------------------------------------------------------------
def extract_layout(pdf_path, topology: dict | None = None, specs: dict | None = None) -> dict:
    """装置図 PDF から機器の位置・高さ・母線を読む。

    specs: 断面の仕様（drawing_rules.section_specs の返り値）。省略時は synth.gen_site.P から作る
           （使うのは断面の枠: 原点・縮尺・y の範囲だけ。機器や鉄構の位置は読まない）。
    返り値のキー: apparatus, heights, buses, arresters, questions, stats
    """
    if specs is None:
        from synth.gen_site import P          # 断面の枠（原点・縮尺・範囲）を得るためだけ
        specs = dr.section_specs(P)
    questions: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        words = _words(page)
        boxes = {n: dr.section_paper_box(specs[n]) for n in dr.SECTION_ORDER}
        plan_x_max = min(b[0] for b in boxes.values()) - 1.0
        plan_words = [w for w in words if w["x"] < plan_x_max]
        bus_lines = {kv: _hlines(page, plan_x_max, dr.BUS_LINEWIDTH_PT[kv]) for kv in dr.BUS_LINEWIDTH_PT}

    # ---- 平面: 機器番号 ----
    by_text: dict[str, list[dict]] = {}
    for w in plan_words:
        by_text.setdefault(w["text"], []).append(w)

    apparatus: list[dict] = []
    unmatched: list[dict] = []      # 番号の形だが結線図に無い文字

    def add(text: str, w: dict, sym: dict, node_id: str | None):
        cx, cy = dr.center_from_text(sym["kind"], (w["x"], w["y"]), sym["along"])
        x0, y0, x1, y1 = SITE_BOX_M
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            questions.append(f"機器番号 {text} の文字から戻した中心 ({cx:.1f}, {cy:.1f}) m が構内の範囲を外れる。記号の種類（{sym['kind']}）が違うか、別の文字かもしれない")
            return
        item = {"number": text, "kind": sym["kind"], "at": [round(cx, 3), round(cy, 3)], "along": sym["along"],
                "text_xy_mm": [round(w["x"], 3), round(w["y"], 3)]}
        if node_id:
            item["id"] = node_id
            item["node_kind"] = sym["node_kind"]
            if sym["kv"]:
                item["kv"] = sym["kv"]
        apparatus.append(item)

    if topology is not None:
        by_label: dict[str, list[dict]] = {}
        for n in topology["nodes"]:
            if n["kind"] in ("disconnector", "breaker", "earthing", "transformer", "load") and _label_of(n):
                by_label.setdefault(_label_of(n), []).append(n)
        for label, nodes in by_label.items():
            hits = by_text.get(label, [])
            if len(nodes) > 1:
                questions.append(f"結線図で番号 {label} が {len(nodes)} 機器（{', '.join(n['id'] for n in nodes)}）に重複している。平面では区別できない")
                continue
            if not hits:
                questions.append(f"結線図の {label}（{nodes[0]['id']}）が平面に見つからない。文字が無いか、読めていない")
                continue
            if len(hits) > 1:
                questions.append(f"番号 {label}（{nodes[0]['id']}）の文字が平面に {len(hits)} 回出ている。どれが機器の番号か確かめること")
                continue
            add(label, hits[0], _symbol_from_topology(nodes[0]), nodes[0]["id"])
        for text in sorted(by_text):
            if NUMBER_RE.match(text) and text not in by_label:
                questions.append(f"平面の文字 {text} は機器番号の形だが結線図に無い")
                unmatched.append({"number": text, "text_xy_mm": [round(by_text[text][0]["x"], 3), round(by_text[text][0]["y"], 3)]})
    else:
        questions.append("結線図が無いので、機器の種類は番号の形から推定した（遮断器・断路器・パンタ型・接地・変圧器・調相設備）。結線図と突き合わせて確かめること")
        for text in sorted(by_text):
            sym = _guess_symbol(text)
            if sym is None:
                continue
            if len(by_text[text]) > 1:
                questions.append(f"番号 {text} の文字が平面に {len(by_text[text])} 回出ている。どれが機器の番号か確かめること")
                continue
            add(text, by_text[text][0], sym, None)

    # ---- 平面: 避雷器 "LA"（位置は規則: 文字は最も東の相の円の右 0.8 m、中心の高さ）----
    arresters = []
    for w in by_text.get("LA", []):
        x_t = (w["x"] - dr.PLAN_OX) / dr.PLAN_SCALE - 0.8              # T 相（東端）の円の中心 x
        y_c = (w["y"] + 1.5 / 2.8 - dr.PLAN_OY) / dr.PLAN_SCALE         # 文字は縦中央揃え（高さ 1.5mm）
        arresters.append({"x_t": round(x_t, 3), "y": round(y_c, 3)})
    arresters.sort(key=lambda a: (a["y"], a["x_t"]))

    # ---- 断面: 高さラベル ----
    heights, bus_hits = [], {}
    n_labels = 0
    for name in dr.SECTION_ORDER:
        sp = specs[name]
        x0, y0, x1, y1 = boxes[name]
        for w in words:
            if not (x0 <= w["x"] <= x1 and y0 <= w["y"] <= y1):
                continue
            p = dr.parse_height_label(w["text"])
            if p is None:
                if "GL+" in w["text"] and not w["text"].startswith("▽"):
                    questions.append(f"断面 {name} の文字「{w['text']}」は高さラベルらしいが形が合わず読めなかった")
                continue
            n_labels += 1
            eid, z = p
            y_m, _ = dr.section_from_mm(sp, w["x"] - HEIGHT_LABEL_DX_MM, w["y"])
            m = BUS_LABEL_RE.match(eid)
            if m:
                bus_hits.setdefault(eid, []).append({"z_m": z, "y_m": y_m, "section": name, "kv": int(m.group(1)), "no": int(m.group(2))})
            else:
                heights.append({"element_id": eid, "z_m": z, "section": name, "y_m": round(y_m, 3)})

    # 同じ要素が複数の断面に出るとき、高さが食い違えば質問
    first: dict[str, dict] = {}
    for h in heights:
        f = first.setdefault(h["element_id"], h)
        if abs(f["z_m"] - h["z_m"]) > 1e-6:
            questions.append(f"{h['element_id']} の高さが断面 {f['section']}（GL+{f['z_m']:.3f} m）と {h['section']}（GL+{h['z_m']:.3f} m）で食い違う")

    # ---- 母線: 高さ（断面）と y・x の範囲（平面の太線）----
    buses = []
    for label, hits in sorted(bus_hits.items(), key=lambda kv: (kv[1][0]["kv"], kv[1][0]["no"])):
        kv, no = hits[0]["kv"], hits[0]["no"]
        zs = {round(h["z_m"], 6) for h in hits}
        if len(zs) > 1:
            questions.append(f"{label} の高さが断面ごとに食い違う: {sorted(zs)}")
        buses.append({"label": label, "kv": kv, "no": no, "z_m": hits[0]["z_m"], "y_m": round(hits[0]["y_m"], 3),
                      "sections": [h["section"] for h in hits], "x_range_m": None, "plan_y_m": None})
    from synth.equipment import EQUIP
    for kv in dr.BUS_LINEWIDTH_PT:
        lines = sorted(bus_lines[kv])                       # (y_mm, x0_mm, x1_mm)
        gap_mm = 2 * EQUIP[kv]["phase_sp"] * dr.PLAN_SCALE   # 相間の 2 倍より離れていれば別の母線
        groups: list[list[tuple]] = []
        for l in lines:
            if groups and l[0] - groups[-1][-1][0] <= gap_mm:
                groups[-1].append(l)
            else:
                groups.append([l])
        for g in groups:
            ys = [(l[0] - dr.PLAN_OY) / dr.PLAN_SCALE for l in g]
            if len(ys) != 3:
                questions.append(f"{kv}kV 母線の太線が {len(ys)} 本しか見つからないまとまりがある（3 相のはず）")
            y_mid = ys[len(ys) // 2]
            x_lo = (min(l[1] for l in g) - dr.PLAN_OX) / dr.PLAN_SCALE
            x_hi = (max(l[2] for l in g) - dr.PLAN_OX) / dr.PLAN_SCALE
            cand = [b for b in buses if b["kv"] == kv and b["x_range_m"] is None]
            if not cand:
                questions.append(f"{kv}kV 母線の太線（y={y_mid:.1f} m）に対応する断面の高さラベルが無い、または既に別の太線が当たっている")
                continue
            b = min(cand, key=lambda b: abs(b["y_m"] - y_mid))
            b["x_range_m"] = [round(x_lo, 3), round(x_hi, 3)]
            b["plan_y_m"] = round(y_mid, 3)
    for b in buses:
        if b["x_range_m"] is None:
            questions.append(f"{b['label']} の平面の太線が見つからない。母線の長さは読めていない")

    stats = {
        "apparatus_found": len(apparatus),
        "height_labels": n_labels,
        "heights_found": len(heights),
        "buses_found": len(buses),
        "arresters_found": len(arresters),
        "questions": len(questions),
    }
    if topology is not None:
        stats["apparatus_expected"] = sum(len(v) for v in by_label.values())
    return {"apparatus": apparatus, "heights": heights, "buses": buses, "arresters": arresters,
            "unmatched_numbers": unmatched, "questions": questions, "stats": stats}
