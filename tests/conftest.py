import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def site():
    from synth.gen_site import build
    return build()


@pytest.fixture(scope="session")
def topo(site):
    from engine.topology import Topology
    return Topology.from_dict(site.topo)


@pytest.fixture(scope="session")
def states(site):
    from synth.gen_site import example_states
    return example_states(site)


def load_schema(name: str) -> dict:
    return json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8"))
