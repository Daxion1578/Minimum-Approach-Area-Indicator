"""単線結線図で作った機器一覧と、平面（機械器具装置図の平面 1/400）の機器が一致しているか。

一般平面図（SITE-01_plan.pdf、1/1000）には開閉器の番号が載っていない（変圧器・調相設備の名前だけ）。
そのため、ここで「平面図」と言うのは装置図の平面 1/400（SITE-01_layout.pdf の左側）を指す。

対象: 断路器・遮断器・接地開閉器・変圧器・調相設備（番号つきの機器）。読み取りと照合は決定論で、Claude は呼ばない。

合成データには今、図面どうしの食い違いが 8 件ある（読み取りの誤りではなく、図面・正解データの側の差）:
  - 単線図だけ: 66kV 母線接地 6A-10E・6B-10E（topology にあるが layout に位置が無く、平面に描かれていない）
  - 平面だけ: 66kV D6（新設予定）の接地開閉器 6 台（topology・平面にあるが、単線図では D6 の接地を描いていない）
下の KNOWN_* がその一覧。生成器（synth/）を直して一致したら、xfail(strict) のテストが XPASS で落ちるので、
KNOWN_* を空にして xfail を外す。
"""
import copy
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "data" / "sites" / "SITE-01"
SLD_PDF = SITE / "drawings" / "SITE-01_sld.pdf"
LAYOUT_PDF = SITE / "drawings" / "SITE-01_layout.pdf"
PLAN_PDF = SITE / "drawings" / "SITE-01_plan.pdf"

KNOWN_ONLY_SLD: list[str] = []
KNOWN_ONLY_PLAN: list[str] = []
KNOWN_NO_AT: list[str] = []          # truth の topology に番号があるのに layout に at が無い
KINDS = ("断路器", "遮断器", "接地開閉器", "変圧器", "調相設備")


@pytest.fixture(scope="module")
def topology():
    return json.loads((SITE / "truth" / "topology.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def truth_layout():
    return json.loads((SITE / "truth" / "layout.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sld_numbers():
    from ingest.pdf_sld import equipment_numbers, extract
    return equipment_numbers(extract(SLD_PDF))


@pytest.fixture(scope="module")
def extracted(topology):
    from ingest.pdf_layout import extract_layout
    return extract_layout(LAYOUT_PDF, topology=topology)


@pytest.fixture(scope="module")
def plan_numbers():
    """結線図を見ずに、平面の文字だけから拾った機器番号。"""
    from ingest.pdf_layout import extract_layout
    return extract_layout(LAYOUT_PDF)["plan_numbers"]


@pytest.fixture(scope="module")
def match(sld_numbers, plan_numbers):
    from ingest.layout_build import match_equipment
    return match_equipment(sld_numbers, plan_numbers)


# ---- 一般平面図には機器番号が無い（だから装置図の平面と照合する）----
def test_general_plan_has_no_switch_numbers():
    import pdfplumber
    from ingest.pdf_layout import _guess_symbol
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        words = {w["text"] for p in pdf.pages for w in p.extract_words()}
    nums = {w for w in words if _guess_symbol(w)}
    assert not any("-" in n for n in nums), f"一般平面図に開閉器番号がある: {sorted(nums)}"


# ---- 図面 PDF から読んだ番号どうし ----
def test_sld_and_plan_read_from_pdfs(match):
    """単線図 147 台・平面 147 台で一致（11/8 に生成器を直して既知の差 8 件を解消）。断路器・遮断器・変圧器・調相設備は種類ごとに台数が一致。"""
    assert match["only_sld"] == KNOWN_ONLY_SLD
    assert match["only_plan"] == KNOWN_ONLY_PLAN
    assert match["matched"] == match["sld"] - len(KNOWN_ONLY_SLD) == match["plan"] - len(KNOWN_ONLY_PLAN)
    assert set(match["by_kind"]) == set(KINDS)
    for k in ("断路器", "遮断器", "変圧器", "調相設備"):
        assert match["by_kind"][k]["sld"] == match["by_kind"][k]["plan"] > 0, k


def test_sld_and_plan_match_completely(match):
    """本人の要望: 単線結線図で作った機器一覧と平面の機器が完全に一致すること。"""
    assert match["ok"], f"単線図だけ {match['only_sld']} ／ 平面だけ {match['only_plan']}"


def test_readers_do_not_lose_numbers(topology, sld_numbers, plan_numbers):
    """食い違いは読み取りのせいではない: 読んだ番号 = 正解 topology の番号 −（その図面に描かれていないもの）。"""
    from ingest.layout_build import topology_numbers
    truth = set(topology_numbers(topology))
    assert truth - set(sld_numbers) == set(KNOWN_ONLY_PLAN) and not set(sld_numbers) - truth
    assert truth - set(plan_numbers) == set(KNOWN_ONLY_SLD) and not set(plan_numbers) - truth


# ---- 読み取りを通さず、正解データ（topology と layout）どうし ----
def test_truth_numbered_nodes_have_position(topology, truth_layout):
    from ingest.layout_build import _KINDS_WITH_NUMBER, _label_of
    numbered = {n["id"] for n in topology["nodes"] if n["kind"] in _KINDS_WITH_NUMBER and _label_of(n)}
    at = {it["id"] for it in truth_layout["items"] if "at" in it}
    assert sorted(numbered - at) == KNOWN_NO_AT
    assert not at - numbered, f"layout に at があるのに番号つきの機器でない: {sorted(at - numbered)}"


def test_truth_numbered_nodes_all_have_position(topology, truth_layout):
    from ingest.layout_build import _KINDS_WITH_NUMBER, _label_of
    numbered = {n["id"] for n in topology["nodes"] if n["kind"] in _KINDS_WITH_NUMBER and _label_of(n)}
    at = {it["id"] for it in truth_layout["items"] if "at" in it}
    assert numbered == at


# ---- わざと 1 台消すと、照合が見つける ----
def test_drop_one_from_plan_is_found(topology, extracted, sld_numbers, plan_numbers):
    from ingest.layout_build import check_consistency, match_equipment
    gone = next(a for a in extracted["apparatus"] if a["number"] == "20E1-110")
    ex = copy.deepcopy(extracted)
    ex["apparatus"] = [a for a in ex["apparatus"] if a["number"] != "20E1-110"]
    miss = [f for f in check_consistency(topology, ex) if f["kind"] == "missing_in_plan"]
    assert gone["id"] in {f["id"] for f in miss}
    m = match_equipment(sld_numbers, [n for n in plan_numbers if n != "20E1-110"])
    assert not m["ok"] and "20E1-110" in m["only_sld"] and m["plan"] == len(plan_numbers) - 1


def test_drop_one_from_sld_is_found(topology, extracted, sld_numbers, plan_numbers):
    from ingest.layout_build import check_consistency, match_equipment
    topo = copy.deepcopy(topology)
    topo["nodes"] = [n for n in topo["nodes"] if n.get("number") != "6T-110"]
    miss = [f for f in check_consistency(topo, extracted) if f["kind"] == "missing_in_sld"]
    assert "6T-110" in {f["id"] for f in miss}
    m = match_equipment([n for n in sld_numbers if n != "6T-110"], plan_numbers)
    assert not m["ok"] and "6T-110" in m["only_plan"]


def test_identical_lists_match():
    from ingest.layout_build import match_equipment
    m = match_equipment(["20E1-110", "1BK", "#1SC"], ["#1SC", "20E1-110", "1BK"])
    assert m == {**m, "sld": 3, "plan": 3, "matched": 3, "ok": True, "only_sld": [], "only_plan": []}


# ---- API: /api/ingest/layout の応答に match が入る ----
@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient
    import server.app as appmod
    monkeypatch.setattr(appmod, "_LAST_SLD", {})
    return TestClient(appmod.app)


def test_api_match_uses_last_read_sld(client):
    r = client.post("/api/ingest/layout", json={"sample": True})
    assert r.status_code == 200 and r.json()["match"]["sld_source"] == "truth"       # 単線図を読む前は正解データと
    with SLD_PDF.open("rb") as f:
        assert client.post("/api/ingest", files={"file": ("sld.pdf", f, "application/pdf")}).status_code == 200
    m = client.post("/api/ingest/layout", json={"sample": True}).json()["match"]
    assert m["sld_source"] == "ingest"
    assert (m["sld"], m["plan"], m["only_sld"], m["only_plan"]) == (147, 147, KNOWN_ONLY_SLD, KNOWN_ONLY_PLAN)


def test_api_match_with_given_numbers(client, plan_numbers):
    m = client.post("/api/ingest/layout", json={"sample": True, "sld_numbers": plan_numbers}).json()["match"]
    assert m["sld_source"] == "request" and m["ok"] and m["sld"] == m["plan"] == 147
