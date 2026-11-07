"""工事の依頼文の読み取り（§8.6）。依頼文（ふつうの日本語）から、取り替える機器・止められない設備・資材置場・重さを取り出す。

Claude に渡すのは、マスクした依頼文と機器の一覧（番号・種別・名前）だけ。Claude が返すのは「どの機器のことか」の候補で、
番号の実在・矛盾の確かめと座標への換算は engine/intake.py（決定論）が行う。画面に入れるのは人が確かめてから。
呼べないときは規則の代替: 文中の開閉器番号だけを拾う（「1 号バンク」のような言い方や、止められない・置き場・重さは読めない）。
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


def catalog(topo: dict) -> list[dict]:
    keep = ("breaker", "disconnector", "transformer", "bus", "source", "load")
    return [{"id": n["id"], "number": n.get("number", ""), "kind": n["kind"], "name": n.get("name", ""), "bay": n.get("bay", "")}
            for n in topo["nodes"] if n["kind"] in keep]


def read_request(text: str, topo: dict) -> dict:
    """依頼文 → 取り出した候補（まだ確かめていない）。source は "claude" か "rules"。"""
    cat = catalog(topo)
    by_num = {c["number"]: c["id"] for c in cat if c["number"]}
    found = [by_num[m] for m in _NUMBER.findall(text) if m in by_num]
    rules = {"source": "rules", "targets": list(dict.fromkeys(found)), "unstoppable": [], "laydown": None, "weight_t": None,
             "questions": ["Claude 未接続のため、文中の開閉器番号だけを拾った。止められない設備・資材置場・重さは読めていない"], "quotes": {}}
    out = client.ask_json("structure", SYSTEM, {"request": text, "equipment": cat}, Mask(), max_tokens=4000)
    if not out:
        return rules
    out["source"] = "claude"
    for k in ("targets", "unstoppable", "questions"):
        if not isinstance(out.get(k), list):
            out[k] = []
    return out
