"""図面取込の意味づけ（§8）。候補グラフ（ingest/pdf_sld.py）を Claude に見せ、種別の確認・名前の補完・人への質問文を作る。

接続（どの導体が何につながるか）はここでは変えない。Claude が返すのは:
  - labels: 開閉器番号ごとの kind（breaker/disconnector/earthing）と、違うと思う理由
  - names: ネットの名前の補完（母線・線路・変圧器一次／二次）
  - questions: 人に確かめてほしいこと（図面の読み取りに自信が無い点）
呼べないときは決定論の規則だけで同じ形を返す（source = "rules"）。
"""
from __future__ import annotations

from agent import client
from agent.mask import Mask
from ingest.pdf_sld import kind_from_number

SYSTEM = """あなたは変電所の単線結線図を読む設計者の助手です。入力は、ベクター PDF から機械的に拾った候補グラフです:
nets（導体のまとまり。bus/line/load/conductor）、switches（開閉器番号と、記号に接する nets）、transformers、questions（機械が迷った点）。
やること:
1. 各開閉器の種別（breaker=遮断器, disconnector=断路器, earthing=接地開閉器）を、番号の形と接続から確かめる。
   規則の目安: 末尾 E は接地、ハイフン後が 3 桁で末尾 0 は遮断器、それ以外は断路器。規則と接続が食い違えば理由を書く。
2. 名前の無い nets に、接続から読める説明（例「東線1L の線路側区間」「2BK 一次」）を付ける。
3. 人に確かめてほしい点を日本語で短く列挙する（番号・場所を具体的に）。
出力は JSON: {"labels":[{"number":..,"kind":..,"note":..}], "names":[{"net":..,"name":..}], "questions":[..], "summary": "一言"}
labels には、規則の目安と違う種別だと思う開閉器だけを入れる（規則どおりのものは書かない）。names は名前の無い主要な nets だけ、20 件まで。
返事は短く。全部を書き写さないこと。
接続そのものは変えないこと。数値や安全判定には触れないこと。"""


def annotate(cand: dict) -> dict:
    rules = {"source": "rules", "labels": [{"number": s["number"], "kind": kind_from_number(s["number"]), "note": ""} for s in cand["switches"]],
             "names": [], "questions": [q["q"] for q in cand.get("questions", [])],
             "summary": f"開閉器 {len(cand['switches'])}、ネット {len(cand['nets'])}、変圧器 {len(cand['transformers'])}。Claude 未使用（キー無し／オフライン）のため規則で種別を付けた"}
    slim = {"nets": cand["nets"], "switches": [{"number": s["number"], "kind_guess": s["kind_guess"], "nets": s.get("nets", [])} for s in cand["switches"]],
            "transformers": cand["transformers"], "lines": [l["name"] for l in cand["lines"]], "questions": cand["questions"]}
    out = client.ask_json("structure", SYSTEM, slim, Mask(), max_tokens=6000)
    if not out:
        return rules
    out["source"] = "claude"
    # Claude の種別が規則と違うときは「要確認」にして人へ（Claude の判断で上書きしない）
    for lab in out.get("labels", []):
        r = kind_from_number(lab["number"])
        if lab.get("kind") != r:
            out.setdefault("questions", []).append(f"{lab['number']} の種別: 規則では {r}、読み取りでは {lab.get('kind')}（{lab.get('note', '')}）。どちらか確かめてほしい")
            lab["kind"] = r
    return out
