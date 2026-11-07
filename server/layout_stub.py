"""装置図の取込（ingest/pdf_layout・layout_build、scripts/eval_layout）が出来るまでの代わり。

truth の layout をそのまま「下書き」として返し、評価は全一致の数字を返す。返り値に "stub": True を付ける。
統合のときにこのファイルごと消し、server/app.py の「装置図（平面・断面）から起こす 3D の下書き」の
import 切り替え（try/except ImportError）を本物だけにする。
"""
from __future__ import annotations

import copy

STUB = True


def extract_layout(pdf_path, topology=None):
    return {"apparatus": [], "heights": [], "buses": [], "questions": [], "stats": {"stub": True}}


def check_consistency(topology, extracted):
    return []


def build_layout(topology, extracted):
    from server.app import load_site   # 循環 import を避けるため遅延
    d = copy.deepcopy(load_site("SITE-01")["layout"])
    d["source"] = "drawing-draft"
    d["questions"] = []
    d["stub"] = True
    return d


def evaluate_layout(draft, truth):
    items = [i for i in truth.get("items", []) if i.get("at")]
    cond = [i for i in truth.get("items", []) if i.get("primitives")]
    return {"apparatus_matched": len(items), "apparatus_total": len(items),
            "position_error_mean_m": 0.0, "position_error_max_m": 0.0,
            "height_matched": len(items), "height_error_mean_m": 0.0, "height_error_max_m": 0.0,
            "conductor_match": {"matched": len(cond), "total": len(cond), "tolerance_m": 0.1}, "stub": True}


def markdown_table(ev):
    return ""
