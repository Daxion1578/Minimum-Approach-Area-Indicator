"""修正案の説明（§7.7）。候補（engine/propose.py。再判定済み）を Claude に見せ、現場の人向けの説明と順位づけの理由を日本語で作る。

判定値・候補の中身はエンジンのもの。Claude は説明と順位の理由だけを返す。呼べないときは定型文。
"""
from __future__ import annotations

from agent import client
from agent.mask import Mask

SYSTEM = """あなたは変電所工事の計画担当を助ける助手です。入力は、クレーン配置の離隔判定（決定論エンジンの結果）と、エンジンが作って再判定した修正案の候補です。
やること: 候補ごとに、現場の人が読んで分かる 1〜2 文の説明（何を変えるか、何が良くなるか、何を犠牲にするか）と、全体の順位づけの理由を書く。
数値・判定は入力のまま使い、新しい数値を作らないこと。追加停止の候補は「停止調整が要る」ことを必ず添えること。
出力は JSON: {"intro": "一言", "items":[{"title": 候補の title, "explain": "..."}], "ranking_note": "..."}"""


def explain(proposal: dict, clearance: dict) -> dict:
    cands = proposal.get("candidates", [])
    fallback = {"source": "rules", "intro": "エンジンが候補を作り、一つずつ再判定した。採用は人が決める。",
                "items": [{"title": c["title"], "explain": _plain(c)} for c in cands],
                "ranking_note": "可 → 条件付き可 → 不可の順。同じ判定なら、追加停止より配置の変更を先に（停止調整が要らないため）、余裕の大きいものを先に"}
    slim = {"baseline": {"verdict": clearance.get("verdict_ja"), "reasons": clearance.get("reasons")},
            "candidates": [{"title": c["title"], "verdict": c["verdict_ja"], "min_distance_m": c["min_distance_m"], "required_m": c["required_m"], "margin_m": c["margin_m"], "conditions": c.get("conditions", []), "kind": c["kind"]} for c in cands]}
    out = client.ask_json("propose", SYSTEM, slim, Mask())
    if not out:
        return fallback
    out["source"] = "claude"
    return out


def _plain(c: dict) -> str:
    base = {"move": "クレーンのベースをずらす。設置場所の地盤と搬入経路を確かめる必要がある",
            "slew": "旋回の範囲を狭める。監視員が旋回の限界を見張り、印を付ける",
            "elev": "ブームを立てる。吊荷の届く範囲が狭まるので、据付位置に届くか確かめる",
            "outage": "充電部そのものを止める。停止調整（系統側との協議）が要る"}[c["kind"]]
    v = f"再判定は {c['verdict_ja']}（最小 {c['min_distance_m']:.2f} m／必要 {c['required_m']:.2f} m）" if c.get("min_distance_m") is not None else f"再判定は {c['verdict_ja']}"
    return f"{base}。{v}"
