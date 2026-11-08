"""v9 の C7: 新しい画面の録画（共通部品は _rec9.py）。"""
import importlib.util
import sys
from pathlib import Path


def make(G):
    m = sys.modules.get("scene__rec9")
    if m is None:
        spec = importlib.util.spec_from_file_location("scene__rec9", Path(__file__).with_name("_rec9.py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules["scene__rec9"] = m
        spec.loader.exec_module(m)
    return m.make(G, "C7")
