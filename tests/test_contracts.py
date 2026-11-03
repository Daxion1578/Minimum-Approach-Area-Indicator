"""契約（contracts/*.schema.json）と、生成器の出力・エンジンの出力が契約に合うことの確認。"""
import json

import jsonschema
import pytest

from conftest import ROOT, load_schema
from engine.energize import energize

SITE_DIR = ROOT / "data" / "sites" / "SITE-01" / "truth"


@pytest.mark.parametrize("name", ["topology", "layout", "state", "energization"])
def test_schema_itself_is_valid(name):
    jsonschema.Draft202012Validator.check_schema(load_schema(name))


def test_generated_topology_and_layout_match_contracts(site):
    jsonschema.validate(site.topo, load_schema("topology"))
    jsonschema.validate(site.layout, load_schema("layout"))


def test_example_states_match_contract_and_cover_all_switches(site, states):
    switch_ids = {n["id"] for n in site.topo["nodes"] if n["kind"] in ("breaker", "disconnector", "earthing")}
    source_ids = {n["id"] for n in site.topo["nodes"] if n["kind"] == "source"}
    for st in states.values():
        jsonschema.validate(st, load_schema("state"))
        assert set(st["switches"]) == switch_ids
        assert set(st["sources"]) == source_ids


def test_energization_output_matches_contract(topo, states):
    for st in states.values():
        jsonschema.validate(energize(topo, st).to_dict(), load_schema("energization"))


def test_layout_items_refer_to_topology_ids(site):
    ids = {n["id"] for n in site.topo["nodes"]} | {e["id"] for e in site.topo["edges"]}
    unknown = [it["id"] for it in site.layout["items"] if it["id"] not in ids]
    assert unknown == []


def test_committed_files_equal_generator_output(site, states):
    """data/sites/SITE-01/truth/ は生成器の出力そのもの（手で直さない）。"""
    if not (SITE_DIR / "topology.json").exists():
        pytest.skip("not generated yet")
    assert json.loads((SITE_DIR / "topology.json").read_text(encoding="utf-8")) == site.topo
    assert json.loads((SITE_DIR / "layout.json").read_text(encoding="utf-8")) == site.layout
    for name, st in states.items():
        assert json.loads((SITE_DIR / "states" / f"{name}.json").read_text(encoding="utf-8")) == st
