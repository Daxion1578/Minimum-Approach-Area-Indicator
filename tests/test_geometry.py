"""幾何（engine/geometry.py）: 線分間距離の 5 ケースとカプセルの隙間。"""
import math

from engine.geometry import capsule_gap, point_segment, segment_segment


def test_parallel_segments():
    d, c1, c2 = segment_segment((0, 0, 0), (10, 0, 0), (0, 3, 0), (10, 3, 0))
    assert math.isclose(d, 3.0)


def test_skew_segments_closest_interior():
    d, c1, c2 = segment_segment((-5, 0, 0), (5, 0, 0), (0, -5, 2), (0, 5, 2))
    assert math.isclose(d, 2.0) and math.isclose(c1[0], 0.0, abs_tol=1e-9) and math.isclose(c2[1], 0.0, abs_tol=1e-9)


def test_endpoint_to_segment():
    d, c1, c2 = segment_segment((0, 0, 0), (1, 0, 0), (5, -1, 0), (5, 1, 0))
    assert math.isclose(d, 4.0) and tuple(c1) == (1.0, 0.0, 0.0) and math.isclose(c2[1], 0.0, abs_tol=1e-9)


def test_endpoint_to_endpoint():
    d, c1, c2 = segment_segment((0, 0, 0), (1, 0, 0), (4, 4, 0), (9, 9, 0))
    assert math.isclose(d, 5.0)


def test_degenerate_points_and_intersection():
    d, _, _ = segment_segment((1, 1, 1), (1, 1, 1), (0, 0, 0), (2, 2, 2))
    assert math.isclose(d, 0.0, abs_tol=1e-9)
    d, _, _ = segment_segment((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0))
    assert math.isclose(d, 0.0, abs_tol=1e-9)


def test_capsule_gap_and_point_segment():
    gap, _, _ = capsule_gap((0, 0, 0), (10, 0, 0), 0.5, (0, 3, 0), (10, 3, 0), 0.5)
    assert math.isclose(gap, 2.0)
    d, c = point_segment((5, 2, 0), (0, 0, 0), (10, 0, 0))
    assert math.isclose(d, 2.0) and tuple(c) == (5.0, 0.0, 0.0)
