"""工事の依頼文の読み取り（agent/intake.py）と確かめ（engine/intake.py）。テストでは Claude を呼ばない（MAAI_OFFLINE=1）。"""
import json

from agent.intake import read_request
from engine.crane_select import select
from engine.intake import check
from engine.steps import generate

TEXT = "次の作業日に、66kV 1号ダイヤの遮断器 6T-110 を取り替えます。新しい遮断器は約 3.5 t です。1号バンクは今回は止められません。"


def _site_dicts(site):
    return json.loads(json.dumps(site.topo)), site.layout


def test_rules_fallback_reads_only_numbers(site):
    topo, _ = _site_dicts(site)
    ext = read_request(TEXT, topo)
    assert ext["source"] == "rules"
    assert ext["targets"] == ["66-D1-CB1"]
    assert ext["unstoppable"] == [] and ext["weight_t"] is None      # 言い方（「1号バンク」）は規則では読めない
    assert "読めていない" in ext["questions"][0]


def test_check_accepts_claude_like_output_and_converts_laydown(site):
    topo, layout = _site_dicts(site)
    ext = {"targets": ["66-D1-CB1"], "unstoppable": ["TR-1"], "weight_t": 3.5,
           "laydown": {"near": "66-D1-CB1", "dir": "west", "dist_m": 8}}
    c = check(ext, topo, layout)
    assert c["ok"] and c["targets"] == ["66-D1-CB1"] and c["unstoppable"] == ["TR-1"] and c["problems"] == []
    at = next(i["at"] for i in layout["items"] if i["id"] == "66-D1-CB1")
    assert c["laydown_xy"] == [round(at[0] - 8, 1), round(at[1], 1)]


def test_check_rejects_unknown_ids_contradictions_and_bad_values(site):
    topo, layout = _site_dicts(site)
    c = check({"targets": ["NO-SUCH"], "unstoppable": []}, topo, layout)
    assert not c["ok"] and any("一覧に無い" in p for p in c["problems"])
    c = check({"targets": ["TR-1"], "unstoppable": ["TR-1"]}, topo, layout)
    assert not c["ok"] and any("両方" in p for p in c["problems"])          # 取り替えると止められないの矛盾
    c = check({"targets": ["66-D1-CB1"], "weight_t": 500, "laydown": {"near": "66-D1-CB1", "dir": "west", "dist_m": 500}}, topo, layout)
    assert c["weight_t"] is None and len(c["problems"]) == 2


def test_unstoppable_equipment_is_never_proposed_for_extra_outage(topo, site, states):
    """依頼文で止められないとされた設備は、追加停止の候補にしない。止められる場合の参考は残す。"""
    day = generate(topo, states["normal"], ["66-D1-CB1"])["state"]
    free = select(topo, site.layout, day, "66-D1-CB1")
    held = select(topo, site.layout, day, "66-D1-CB1", unstoppable=["TR-1"])
    assert free["with_outage"]["chosen"] and "TR-1" in free["with_outage"]["targets"]
    wo = held["with_outage"]
    assert wo["blocked"] == ["TR-1"] and wo["chosen"] is None and wo["ops"] == []
    assert "止められない" in wo["note"] and "止められるなら" in wo["note"]
    assert held["chosen"]["class"] == free["chosen"]["class"]               # 選んだクラスそのものは変わらない
