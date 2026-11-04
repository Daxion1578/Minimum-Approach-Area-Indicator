"""幾何（§7.2）。線分どうしの最短距離と、その最近点。カプセル（線分＋半径）どうしの隙間。

純粋な計算だけ。座標は構内ローカル（m）。
"""
from __future__ import annotations

import math
from typing import Sequence

Vec = tuple[float, float, float]


def _sub(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Sequence[float], k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm(a: Sequence[float]) -> float:
    return math.sqrt(_dot(a, a))


def segment_segment(p1: Sequence[float], q1: Sequence[float], p2: Sequence[float], q2: Sequence[float]) -> tuple[float, Vec, Vec]:
    """線分 p1-q1 と p2-q2 の最短距離と、その最近点（c1 on 1, c2 on 2）。
    Ericson, Real-Time Collision Detection 5.1.9 の方法。退化（点）にも対応。"""
    d1 = _sub(q1, p1)
    d2 = _sub(q2, p2)
    r = _sub(p1, p2)
    a = _dot(d1, d1)
    e = _dot(d2, d2)
    f = _dot(d2, r)
    EPS = 1e-12
    if a <= EPS and e <= EPS:
        s = t = 0.0
    elif a <= EPS:
        s = 0.0
        t = min(max(f / e, 0.0), 1.0)
    else:
        c = _dot(d1, r)
        if e <= EPS:
            t = 0.0
            s = min(max(-c / a, 0.0), 1.0)
        else:
            b = _dot(d1, d2)
            denom = a * e - b * b
            s = min(max((b * f - c * e) / denom, 0.0), 1.0) if denom > EPS else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t = 0.0
                s = min(max(-c / a, 0.0), 1.0)
            elif t > 1.0:
                t = 1.0
                s = min(max((b - c) / a, 0.0), 1.0)
    c1 = _add(p1, _mul(d1, s))
    c2 = _add(p2, _mul(d2, t))
    return norm(_sub(c1, c2)), c1, c2


def capsule_gap(a1, b1, r1: float, a2, b2, r2: float) -> tuple[float, Vec, Vec]:
    """カプセルどうしの表面間の隙間（負なら食い込み）と、軸上の最近点。"""
    d, c1, c2 = segment_segment(a1, b1, a2, b2)
    return d - r1 - r2, c1, c2


def point_segment(p: Sequence[float], a: Sequence[float], b: Sequence[float]) -> tuple[float, Vec]:
    d, _, c2 = segment_segment(p, p, a, b)
    return d, c2
