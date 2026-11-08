"""工事の依頼文の読み取り（§8.6）。依頼文（ふつうの日本語）から、取り替える機器・止められない設備・資材置場・重さを取り出す。

Claude に渡すのは、マスクした依頼文と機器の一覧（番号・種別・名前）だけ。Claude が返すのは「どの機器のことか」の候補で、
番号の実在・矛盾の確かめと座標への換算は engine/intake.py（決定論）が行う。画面に入れるのは人が確かめてから。
呼べないときは規則の代替: 決まった書き方だけを拾う。開閉器の番号、「〜は止められません」の文に出る設備の名前、
「〜の西側、6 m」の置き場（基準は文中の番号、無ければ取り替える機器）、「約 10 t」の重さ。言い換え（「1 号バンク」など）は読めない。
どちらで読んでも、確かめは engine/intake.py、入れるかは人が決める。
"""
from __future__ import annotations

import re

from agent import client
from agent.mask import Mask

SYSTEM = """あなたは変電所の工事担当の助手です。入力は、工事の依頼文（request）と、構内の機器の一覧（equipment: number=図面の番号, id, kind, name, bay）です。
依頼文から次を取り出し、機器は必ず一覧の id で答えてください（一覧に無いものは作らない。迷ったら questions に書く）。
- targets: その作業日に取り替える機器の id（遮断器 breaker・断路器 disconnector など）
- unstoppable: 依頼文で「止められない」「運転を続ける」とされている設備の id（変圧器 transformer・母線 bus・線路 source など）
- laydown: 資材置場。{"near": 基準にする機器の id, "dir": "east|west|north|south", "dist_m": 数値}。書かれていなければ null
- weight_t: 吊る機器の重さ（t）。書かれていなければ null
- questions: 人に確かめてほしいこと（あいまいな言い方、一覧に見つからない設備など）を日本語で短く
- quotes: 取り出した各項目の根拠になった依頼文の一節（"targets"/"unstoppable"/"laydown"/"weight_t" をキーに）
言い換えの例: 「1号バンク」「1BK」「1号変圧器」は同じ変圧器。「〜線」は線路（source）。
出力は JSON: {"targets":[..],"unstoppable":[..],"laydown":{..}|null,"weight_t":数値|null,"questions":[..],"quotes":{..}}
安全の判定や数値の計算はしないこと。"""

_NUMBER = re.compile(r"\b\d{1,2}[A-Z][A-Z0-9]*-\d{3,4}E?\b")
_HOLD = re.compile(r"止められ(?:ない|ません)|運転を続け")
_DIR = {"東": "east", "西": "west", "南": "south", "北": "north"}
_LAYDOWN = re.compile(r"(東|西|南|北)側[、,\s]*(?:約)?\s*(\d+(?:\.\d+)?)\s*(?:m|ｍ|メートル)")
_WEIGHT = re.compile(r"(?:重さ|重量|は)[はがの]?\s*約?\s*(\d+(?:\.\d+)?)\s*(?:t|ｔ|トン)(?!\s*級)(?![A-Za-z])")


def catalog(topo: dict) -> list[dict]:
    keep = ("breaker", "disconnector", "transformer", "bus", "source", "load")
    return [{"id": n["id"], "number": n.get("number", ""), "kind": n["kind"], "name": n.get("name", ""), "bay": n.get("bay", "")}
            for n in topo["nodes"] if n["kind"] in keep]


def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _sentences(text: str) -> list[str]:
    return [s.strip() + "。" for s in re.split(r"[。\n]", text) if s.strip()]


def _rules(text: str, cat: list[dict]) -> dict:
    """Claude を呼べないときの読み取り。決まった書き方だけ。読めなかった項目は None / [] のまま（人が STEP 3 で入れる）。"""
    by_num = {c["number"]: c["id"] for c in cat if c["number"]}
    targets = list(dict.fromkeys(by_num[m] for m in _NUMBER.findall(text) if m in by_num))
    quotes: dict[str, str] = {}
    if targets:
        quotes["targets"] = next((s for s in _sentences(text) if any(m in by_num for m in _NUMBER.findall(s))), "")
    # 止められない設備: その文に出る設備の名前（空白を詰めて比べる）か番号。変圧器は「1号変圧器」の部分だけでもよい
    names = []
    for c in cat:
        if c["kind"] not in ("bus", "transformer", "source", "load"):
            continue
        keys = [_flat(c["name"])] if c["name"] else []
        if c["kind"] == "transformer" and c["name"]:
            keys.append(_flat(c["name"].split()[0]))
        if c["number"]:
            keys.append(c["number"])
        names.append((c["id"], [k for k in keys if len(k) >= 3]))
    unstoppable, held = [], []
    for s in _sentences(text):
        if not _HOLD.search(s):
            continue
        fs = _flat(s)
        hit = [i for i, keys in names if any(k in fs for k in keys)]   # 開閉器の番号は拾わない（操作の文に出やすい）
        if hit:
            unstoppable += hit; held.append(s)
    unstoppable = list(dict.fromkeys(unstoppable))   # 取り替える機器と重なれば engine/intake.py が矛盾として出す
    if held:
        quotes["unstoppable"] = " ".join(held)
    laydown = None
    for s in _sentences(text):
        m = _LAYDOWN.search(s)
        if not m:
            continue
        near = next((by_num[n] for n in _NUMBER.findall(s[:m.start()]) if n in by_num), targets[0] if targets else None)
        if near:
            laydown = {"near": near, "dir": _DIR[m.group(1)], "dist_m": float(m.group(2))}
            quotes["laydown"] = s
        break
    weight = None
    for s in _sentences(text):
        m = _WEIGHT.search(s)
        if m:
            weight = float(m.group(1)); quotes["weight_t"] = s
            break
    q = ["Claude につながっていないので、決まった書き方だけを規則で読んだ（番号、「〜は止められません」、「〜の西側、6 m」、「約 10 t」）。"
         "言い換え（「1 号バンク」など）は読めない。原文と並べて確かめる"]
    q += [f"{k}は読めなかった（STEP 3 で入れる）" for k, v in (("資材置場", laydown), ("重さ", weight)) if v is None]
    return {"source": "rules", "targets": targets, "unstoppable": unstoppable, "laydown": laydown, "weight_t": weight,
            "questions": q, "quotes": quotes}


def read_request(text: str, topo: dict) -> dict:
    """依頼文 → 取り出した候補（まだ確かめていない）。source は "claude" か "rules"。"""
    cat = catalog(topo)
    rules = _rules(text, cat)
    out = client.ask_json("structure", SYSTEM, {"request": text, "equipment": cat}, Mask(), max_tokens=4000)
    if not out:
        return rules
    out["source"] = "claude"
    for k in ("targets", "unstoppable", "questions"):
        if not isinstance(out.get(k), list):
            out[k] = []
    return out
