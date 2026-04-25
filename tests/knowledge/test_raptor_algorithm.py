"""P24.M4 RAPTOR 核心算法 —— pure-numpy kmeans + 树构建（mock LLM/embed）。"""
from __future__ import annotations

import uuid

import numpy as np
import pytest

from app.knowledge.chunking.raptor import (
    RaptorSeed,
    _kmeans,
    _pick_k,
    build_raptor_levels,
)


# ─── k-means sanity ──────────────────────────────────────────────

def test_kmeans_separates_two_clusters():
    rng = np.random.default_rng(0)
    cluster_a = rng.normal(loc=0, scale=0.1, size=(20, 5))
    cluster_b = rng.normal(loc=10, scale=0.1, size=(20, 5))
    vectors = np.vstack([cluster_a, cluster_b])
    labels = _kmeans(vectors, k=2, seed=42)
    # 同一簇内 label 应当相同（允许被调换 0↔1）
    first_half_labels = set(labels[:20].tolist())
    second_half_labels = set(labels[20:].tolist())
    assert len(first_half_labels) == 1
    assert len(second_half_labels) == 1
    assert first_half_labels != second_half_labels


def test_kmeans_k_greater_than_n_returns_trivial():
    vectors = np.eye(3)  # 3 samples
    labels = _kmeans(vectors, k=10)
    assert labels.tolist() == [0, 1, 2]


def test_pick_k_bounds():
    assert _pick_k(1) == 1  # 太少 → 跳过聚类
    assert _pick_k(3) == 1
    assert _pick_k(8) >= 2
    assert _pick_k(5000) <= 20  # 上限


# ─── build_raptor_levels ─────────────────────────────────────────

def _seed(i: int, cluster: int) -> RaptorSeed:
    base = np.zeros(4)
    base[cluster] = 1.0
    return RaptorSeed(
        id=uuid.uuid4(),
        content=f"chunk {i} of cluster {cluster}",
        embedding=base + np.random.default_rng(i).normal(0, 0.01, size=4),
    )


@pytest.mark.asyncio
async def test_build_raptor_levels_produces_summaries():
    # 12 seeds 分布在 3 个明显的簇
    seeds = []
    for c in range(3):
        for i in range(4):
            seeds.append(_seed(i * 10 + c, c))

    summarize_calls: list[list[str]] = []
    async def summarize_fn(texts: list[str]) -> str:
        summarize_calls.append(texts)
        return f"SUMMARY-of-{len(texts)}"

    async def embed_fn(texts: list[str]) -> list[list[float]]:
        # 为下一轮返回"各摘要不同方向"的假向量，避免再聚到一簇
        return [[float(i == j) for j in range(len(texts))] for i in range(len(texts))]

    summaries = await build_raptor_levels(
        seeds, summarize_fn=summarize_fn, embed_fn=embed_fn,
        max_levels=2, min_cluster_size=2,
    )
    assert len(summaries) >= 1
    assert all(s.summary.startswith("SUMMARY-of-") for s in summaries)
    assert all(s.level >= 1 for s in summaries)
    # member_ids 覆盖输入 seed
    covered = {m for s in summaries if s.level == 1 for m in s.member_ids}
    seed_ids = {s.id for s in seeds}
    assert covered.issubset(seed_ids)


@pytest.mark.asyncio
async def test_build_raptor_empty_input_returns_empty():
    async def _nop(_t):
        return ""
    out = await build_raptor_levels(
        [], summarize_fn=_nop, embed_fn=_nop, max_levels=3,
    )
    assert out == []


@pytest.mark.asyncio
async def test_build_raptor_bail_on_too_few_seeds():
    seeds = [_seed(0, 0), _seed(1, 0)]  # 只够一个簇
    async def _nop(_t):
        return "s"
    out = await build_raptor_levels(
        seeds, summarize_fn=_nop, embed_fn=_nop, max_levels=3, min_cluster_size=2,
    )
    # 2 seeds 不够走聚类流程（需要 min_cluster_size * 2 = 4），直接返回空
    assert out == []


@pytest.mark.asyncio
async def test_build_raptor_summarize_failure_skips_cluster():
    seeds = [_seed(i, i % 2) for i in range(8)]

    call_count = {"n": 0}
    async def summarize_fn(texts):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("LLM timeout")
        return "OK"

    async def embed_fn(texts):
        return [[1.0, 0.0] for _ in texts]

    out = await build_raptor_levels(
        seeds, summarize_fn=summarize_fn, embed_fn=embed_fn,
        max_levels=1, min_cluster_size=2,
    )
    # 第一簇失败被跳过，其他簇 / 后续层正常
    assert all(s.summary == "OK" for s in out)
