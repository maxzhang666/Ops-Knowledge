"""Plan 26 M1/M5 — redundancy 算法纯函数测试（numpy-only，无 Milvus/DB）。"""
from __future__ import annotations

import numpy as np
import pytest

from app.knowledge.coverage.redundancy import (
    DEFAULT_THRESHOLD,
    find_redundant_pairs,
)


def _vec(angle_deg: float) -> list[float]:
    t = np.deg2rad(angle_deg)
    return [float(np.cos(t)), float(np.sin(t))]


def test_identical_vectors_found():
    ids = ["a", "b", "c"]
    vectors = np.array([_vec(0), _vec(0), _vec(90)], dtype=np.float32)
    pairs = find_redundant_pairs(ids, vectors, threshold=0.99)
    assert len(pairs) == 1
    assert {pairs[0].a_id, pairs[0].b_id} == {"a", "b"}
    assert pairs[0].similarity > 0.99


def test_below_threshold_dropped():
    ids = ["a", "b"]
    # 60 度 → cos = 0.5
    vectors = np.array([_vec(0), _vec(60)], dtype=np.float32)
    pairs = find_redundant_pairs(ids, vectors, threshold=0.9)
    assert pairs == []


def test_returns_sorted_desc():
    ids = ["a", "b", "c", "d"]
    vectors = np.array([
        _vec(0),
        _vec(1),   # 与 a 很近
        _vec(5),   # 与 a 中等近
        _vec(180), # 反向
    ], dtype=np.float32)
    pairs = find_redundant_pairs(ids, vectors, threshold=0.99)
    # (a,b) 更近，应排在 (a,c) 之前
    assert len(pairs) >= 2
    for i in range(len(pairs) - 1):
        assert pairs[i].similarity >= pairs[i + 1].similarity


def test_pair_ordering_a_lt_b_is_not_enforced_here():
    # find_redundant_pairs 只保证 i < j 对 ids 的输入顺序，不检查字符串字典序
    # （字典序排序由 Celery 任务入库前处理）
    ids = ["zzz", "aaa"]
    vectors = np.array([_vec(0), _vec(0.5)], dtype=np.float32)
    pairs = find_redundant_pairs(ids, vectors, threshold=0.99)
    assert len(pairs) == 1
    assert pairs[0].a_id == "zzz"  # 输入顺序 i=0
    assert pairs[0].b_id == "aaa"


def test_single_vector_returns_empty():
    assert find_redundant_pairs(["x"], np.array([_vec(0)]), threshold=0.5) == []


def test_empty_returns_empty():
    assert find_redundant_pairs([], np.zeros((0, 2)), threshold=0.5) == []


def test_block_size_does_not_change_result():
    ids = [f"c{i}" for i in range(50)]
    rng = np.random.default_rng(7)
    vectors = rng.normal(size=(50, 8)).astype(np.float32)
    a = find_redundant_pairs(ids, vectors, threshold=0.8, block_size=8)
    b = find_redundant_pairs(ids, vectors, threshold=0.8, block_size=256)
    assert {(p.a_id, p.b_id) for p in a} == {(p.a_id, p.b_id) for p in b}


def test_shape_mismatch_raises():
    with pytest.raises(ValueError):
        find_redundant_pairs(["a", "b"], np.array([_vec(0)]), threshold=0.5)


def test_default_threshold_is_0_92():
    # Cement the business rule
    assert DEFAULT_THRESHOLD == 0.92
