"""Plan 31 M4 — find_cross_kb_pairs 纯函数测试。"""
from __future__ import annotations

import numpy as np
import pytest

from app.knowledge.coverage.cross_kb import (
    CROSS_DEFAULT_THRESHOLD,
    CrossKBPair,
    find_cross_kb_pairs,
)


def _vec(angle_deg: float) -> list[float]:
    t = np.deg2rad(angle_deg)
    return [float(np.cos(t)), float(np.sin(t))]


def test_identical_vectors_match():
    pairs = find_cross_kb_pairs(
        ["a"], np.array([_vec(0)], dtype=np.float32),
        ["b"], np.array([_vec(0)], dtype=np.float32),
        threshold=0.99,
    )
    assert len(pairs) == 1
    assert pairs[0].similarity > 0.99


def test_orthogonal_vectors_dropped():
    pairs = find_cross_kb_pairs(
        ["a"], np.array([_vec(0)], dtype=np.float32),
        ["b"], np.array([_vec(90)], dtype=np.float32),
        threshold=0.5,
    )
    assert pairs == []


def test_pairs_sorted_desc_and_capped():
    ids_a = [f"a{i}" for i in range(3)]
    ids_b = [f"b{i}" for i in range(3)]
    a = np.array([_vec(0), _vec(1), _vec(5)], dtype=np.float32)
    b = np.array([_vec(0), _vec(2), _vec(10)], dtype=np.float32)
    pairs = find_cross_kb_pairs(
        ids_a, a, ids_b, b, threshold=0.95, max_pairs=4,
    )
    assert len(pairs) <= 4
    for i in range(len(pairs) - 1):
        assert pairs[i].similarity >= pairs[i + 1].similarity


def test_no_chunks_returns_empty():
    out = find_cross_kb_pairs([], np.zeros((0, 2)), ["b"], np.array([_vec(0)]))
    assert out == []


def test_dim_mismatch_raises():
    with pytest.raises(ValueError):
        find_cross_kb_pairs(
            ["a", "b"], np.array([_vec(0)]),  # length mismatch
            ["c"], np.array([_vec(0)]),
        )


def test_default_threshold_is_0_85():
    # Cement business rule: cross-KB stricter than redundancy default 0.92? 不，
    # cross-KB 默认更宽松（0.85），因为不同知识库自然存在表述差异。
    assert CROSS_DEFAULT_THRESHOLD == 0.85


def test_pair_dataclass_carries_ids():
    p = CrossKBPair(a_id="x", b_id="y", similarity=0.9)
    assert p.a_id == "x"
    assert p.b_id == "y"
    assert p.similarity == 0.9
