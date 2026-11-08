"""工事の依頼文の読み取り（agent/intake.py）と確かめ（engine/intake.py）。テストでは Claude を呼ばない（MAAI_OFFLINE=1）。"""
import json

from agent.intake import read_request
from engine.crane_select import select
from engine.intake import check
from engine.steps import generate

TEXT = "次の作業日に、66kV 1号ダイヤの遮断器 6T-110 を取り替えます。新しい遮断器は約 3.5 t です。1号バンクは今回は止められません。"


def _site_dicts(site):
    return json.loads(json.dumps(site.topo)), site.layout


def test_rules_fallback_reads_fixed_phrases_but_not_paraphrases(site):
    topo, _ = _site_dicts(site)
    ext = read_request(TEXT, topo)
    assert ext["source"] == "rules"
    assert ext["targets"] == ["66-D1-CB1"]
    assert ext["weight_t"] == 3.5                                     # 「約 3.5 t」は決まった書き方
    assert ext["unstoppable"] == []                                   # 言い換え（「1号バンク」）は規則では読めない
    assert ext["laydown"] is None and any("資材置場は読めなかった" in q for q in ext["questions"])
    assert "決まった書き方" in ext["questions"][0]


SAMPLE = ("次の作業日に、220kV 東線1L の遮断器 20E1-110 を取り替えます。新しい遮断器は約 10 t です。"
          "資材は取り替える遮断器の西側、6 m ほど離れた空き地に仮置きします。東線1L は相手端も含めて停止します。"
          "220kV 母線 A 区間は系統の都合で今回は止められません。")   # 画面の見本の依頼文（web/index.html）と同じ


def test_rules_fallback_reads_the_sample_request_like_claude(site):
    """Claude につながらない公開版でも、見本の依頼文から同じ 4 項目が読める。止める案を出すかの答えも同じになる。"""
    topo, layout = _site_dicts(site)
    ext = read_request(SAMPLE, topo)
    assert ext["source"] == "rules"
    assert ext["targets"] == ["220-L1-CB"]
    assert ext["unstoppable"] == ["220-BUS-A"]                        # 「東線1L は…停止します」は止められない側に入れない
    assert ext["laydown"] == {"near": "220-L1-CB", "dir": "west", "dist_m": 6.0}
    assert ext["weight_t"] == 10.0
    assert "止められません" in ext["quotes"]["unstoppable"] and "西側" in ext["quotes"]["laydown"]
    c = check(ext, topo, layout)
    at = next(i["at"] for i in layout["items"] if i["id"] == "220-L1-CB")
    assert c["ok"] and c["problems"] == [] and c["laydown_xy"] == [round(at[0] - 6, 1), round(at[1], 1)]


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
