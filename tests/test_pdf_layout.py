"""装置図 PDF → 機器の位置・高さ → 3D レイアウトの組み直し（ingest/pdf_layout.py, layout_build.py, scripts/eval_layout.py）。

正解は data/sites/SITE-01/truth/layout.json。読み取りと組み立ては決定論で、Claude は呼ばない。
"""
import copy
import json
import math
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

SITE = ROOT / "data" / "sites" / "SITE-01"
PDF = SITE / "drawings" / "SITE-01_layout.pdf"


@pytest.fixture(scope="module")
def topology():
    return json.loads((SITE / "truth" / "topology.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def truth():
    return json.loads((SITE / "truth" / "layout.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def extracted(topology):
    from ingest.pdf_layout import extract_layout
    return extract_layout(PDF, topology=topology)


@pytest.fixture(scope="module")
def draft(topology, extracted):
    from ingest.layout_build import build_layout
    return build_layout(topology, extracted)


def test_all_apparatus_found_with_small_position_error(extracted, truth):
    at = {i["id"]: i["at"] for i in truth["items"] if "at" in i}
    assert len(at) == 145
    assert extracted["stats"]["apparatus_found"] == 145
    found = {a["id"]: a for a in extracted["apparatus"]}
    assert set(found) == set(at)
    worst = max(math.hypot(found[k]["at"][0] - at[k][0], found[k]["at"][1] - at[k][1]) for k in at)
    assert worst < 0.05


def test_height_label_count(extracted):
    # 断面ごとの高さラベル: A-A 23、B-B 7、C-C 16（scripts/check_drawing_rules.py と同じ数）。うち母線 3+1+2
    assert extracted["stats"]["height_labels"] == 23 + 7 + 16
    assert len(extracted["heights"]) == 46 - 6
    assert {(b["kv"], b["no"]) for b in extracted["buses"]} == {(220, 1), (66, 1), (66, 2)}
    sections = {h["section"] for h in extracted["heights"]}
    assert sections == {"A-A", "B-B", "C-C"}


def test_bus_heights_and_plan_ranges(extracted):
    b = {x["label"]: x for x in extracted["buses"]}
    assert b["220kV 1号母線"]["z_m"] == 10.5 and b["220kV 1号母線"]["x_range_m"] == [22.0, 126.0]
    assert b["66kV 1号母線"]["z_m"] == 6.5 and b["66kV 2号母線"]["z_m"] == 4.5


def test_build_layout_counts_match_truth(draft, truth):
    assert draft["source"] == "drawing-draft"
    assert isinstance(draft["questions"], list)
    t_app = [i for i in truth["items"] if "at" in i]
    d_app = [i for i in draft["items"] if "at" in i]
    assert len(d_app) == len(t_app)
    assert all(i["height_source"] in ("drawing", "library") for i in d_app)
    count = lambda lay: sum(len(i["primitives"]) for i in lay["items"])
    assert count(draft) == count(truth)
    assert len(draft["structures"]) == len(truth["structures"])


def test_to_contract_validates_against_schema(draft):
    jsonschema = pytest.importorskip("jsonschema")
    from ingest.layout_build import to_contract
    schema = json.loads((ROOT / "contracts" / "layout.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(to_contract(draft), schema)


def test_conductor_match_rate(draft, truth):
    from eval_layout import evaluate_layout, markdown_table
    res = evaluate_layout(draft, truth)
    print("\n" + markdown_table(res))
    c = res["conductor_match"]
    rate = c["matched"] / c["total"]
    print(f"導体の一致率 {rate:.3f}（{c['matched']}/{c['total']}、許容 {c['tolerance_m']} m）")
    assert res["apparatus_matched"] == res["apparatus_total"] == 145
    assert res["height_matched"] == res["apparatus_total"]
    assert rate >= 0.9


def test_consistency_on_site01(topology, extracted):
    from ingest.layout_build import check_consistency
    res = check_consistency(topology, extracted)
    kinds = {}
    for f in res:
        kinds.setdefault(f["kind"], []).append(f["id"])
    # 66kV 母線の接地開閉器は平面に番号が無い（truth でも at を持たない）
    assert sorted(kinds["missing_in_plan"]) == ["66-BUS-A-ES", "66-BUS-B-ES"]
    assert "missing_in_sld" not in kinds
    assert len(kinds["no_height"]) > 0


def test_consistency_flags_invented_node(topology, extracted):
    from ingest.layout_build import check_consistency
    topo2 = copy.deepcopy(topology)
    topo2["nodes"].append({"id": "220-X9-CB", "kind": "breaker", "voltage_kv": 220, "number": "20X9-110"})
    res = check_consistency(topo2, extracted)
    hit = [f for f in res if f["kind"] == "missing_in_plan" and f["id"] == "220-X9-CB"]
    assert len(hit) == 1 and hit[0]["message"]


def test_consistency_flags_number_missing_in_sld(topology, extracted):
    from ingest.layout_build import check_consistency
    topo2 = copy.deepcopy(topology)
    gone = next(n for n in topo2["nodes"] if n.get("number") == "6T-110")
    topo2["nodes"].remove(gone)
    res = check_consistency(topo2, extracted)
    assert any(f["kind"] == "missing_in_sld" and f["id"] == "6T-110" for f in res)


def test_incomplete_plan_makes_no_dangling_conductors(topology, extracted):
    """平面から機器が 1 台落ちたら、その機器につながる導体は作らず、質問に出す（充電扱いにもしない）。"""
    from ingest.layout_build import build_layout
    ex2 = copy.deepcopy(extracted)
    ex2["apparatus"] = [a for a in ex2["apparatus"] if a["number"] != "6T-110"]
    d = build_layout(topology, ex2)
    ids = {i["id"] for i in d["items"]}
    assert "66-D1-CB1" not in {i["id"] for i in d["items"] if "at" in i}
    assert "66-D1-N1" not in ids and "66-D1-N6" not in ids
    assert any("66-D1-CB1" in q for q in d["questions"])


def test_extract_without_topology_guesses_kinds(extracted):
    from ingest.pdf_layout import extract_layout
    ex = extract_layout(PDF)
    assert ex["stats"]["apparatus_found"] >= 143
    assert any("推定" in q for q in ex["questions"])
    with_topo = {a["number"]: a for a in extracted["apparatus"]}
    for a in ex["apparatus"]:
        assert a["kind"] == with_topo[a["number"]]["kind"], a["number"]
