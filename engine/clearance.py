"""離隔判定（§7.5）。重機の包絡と充電導体の包絡の最短距離から、可／条件付き可／不可と根拠を出す。

判定の規則（data/rules/clearance_rules.json に無ければ既定）:
  R1  重機の包絡（ブーム・ロープ・吊荷・車体）と充電導体の表面間距離 d が、電圧階級の離隔 c 以上なら可
  R2  d < c なら不可
  R6  可でも余裕 d − c が margin_m（既定 0.5m）未満なら「条件付き可」。条件: 監視員を置く、旋回角を印で示す
判定はすべて決定論。Claude は判定値を決めない（提案だけ）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from engine.crane import Crane
from engine.geometry import capsule_gap

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data" / "rules" / "clearance_rules.json"
DEFAULT_RULES = {"margin_m": 0.5, "slew_step_deg": 5.0,
                 "conditions_when_marginal": ["監視員を置き、旋回の限界を見張る", "旋回角の限界を車体と地面に印で示す"]}

OK, CONDITIONAL, NG = "ok", "conditional", "ng"
VERDICT_JA = {OK: "可", CONDITIONAL: "条件付き可", NG: "不可"}


def load_rules() -> dict:
    if RULES.exists():
        return {**DEFAULT_RULES, **json.loads(RULES.read_text(encoding="utf-8"))}
    return dict(DEFAULT_RULES)


@dataclass
class Hit:
    conductor_id: str
    phase: str | None
    voltage_kv: float
    required_m: float
    distance_m: float
    crane_part: str
    slew_deg: float | None
    p_crane: list[float]
    p_conductor: list[float]

    @property
    def margin_m(self) -> float:
        return round(self.distance_m - self.required_m, 3)

    def to_dict(self) -> dict:
        return {"conductor_id": self.conductor_id, "phase": self.phase, "voltage_kv": self.voltage_kv,
                "required_m": self.required_m, "distance_m": round(self.distance_m, 3), "margin_m": self.margin_m,
                "crane_part": self.crane_part, "slew_deg": self.slew_deg,
                "p_crane": [round(v, 3) for v in self.p_crane], "p_conductor": [round(v, 3) for v in self.p_conductor]}


def evaluate(envelope: dict, crane: Crane, rules: dict | None = None) -> dict:
    """§6.7 clearance.json。envelope は §6.5（承認前）、crane は配置。"""
    rules = rules or load_rules()
    crane_caps = crane.sweep(rules["slew_step_deg"])
    best: dict[tuple[str, str | None], Hit] = {}
    for env in envelope["envelopes"]:
        pr = env["primitive"]
        cond_r = pr["r"] - env["clearance_m"]          # 導体そのものの半径
        key = (env["conductor_id"], pr.get("phase"))
        for cc in crane_caps:
            gap, pc, pk = capsule_gap(cc["a"], cc["b"], cc["r"], pr["a"], pr["b"], cond_r)
            if key not in best or gap < best[key].distance_m:
                best[key] = Hit(env["conductor_id"], pr.get("phase"), env["voltage_kv"], env["clearance_m"], gap,
                                cc["part"], cc["slew_deg"], list(pc), list(pk))
    hits = sorted(best.values(), key=lambda h: h.margin_m)
    verdict = OK
    reasons: list[str] = []
    conditions: list[str] = []
    if hits:
        worst = hits[0]
        if worst.margin_m < 0:
            verdict = NG
            reasons.append(f"R2: {worst.conductor_id}（{worst.phase} 相、{worst.voltage_kv:g}kV）に {worst.crane_part} が {worst.distance_m:.2f}m まで近づく。必要 {worst.required_m:.2f}m"
                           + (f"（旋回 {worst.slew_deg:+.0f}°）" if worst.slew_deg is not None else ""))
        elif worst.margin_m < rules["margin_m"]:
            verdict = CONDITIONAL
            reasons.append(f"R6: 最小離隔 {worst.distance_m:.2f}m は必要 {worst.required_m:.2f}m を満たすが、余裕 {worst.margin_m:.2f}m が {rules['margin_m']:.1f}m 未満"
                           + (f"（{worst.conductor_id} {worst.phase} 相、旋回 {worst.slew_deg:+.0f}°）" if worst.slew_deg is not None else ""))
            conditions = list(rules["conditions_when_marginal"])
        else:
            reasons.append(f"R1: 最小離隔 {worst.distance_m:.2f}m（{worst.conductor_id} {worst.phase} 相）は必要 {worst.required_m:.2f}m を余裕 {worst.margin_m:.2f}m で満たす")
    else:
        reasons.append("充電導体の包絡が無い（全停止）")
    return {
        "schema_version": "0.1", "site_id": envelope.get("site_id"), "step": envelope.get("step"),
        "crane": crane.to_dict(), "rules": {k: rules[k] for k in ("margin_m", "slew_step_deg")},
        "verdict": verdict, "verdict_ja": VERDICT_JA[verdict], "reasons": reasons, "conditions": conditions,
        "worst": hits[0].to_dict() if hits else None,
        "hits": [h.to_dict() for h in hits[:20]],
        "ng_count": sum(1 for h in hits if h.margin_m < 0),
        "crane_capsules": crane_caps,
    }
