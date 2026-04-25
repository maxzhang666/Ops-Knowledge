"""Plan 26 T5 — topic 聚类 + 标签解析纯函数测试。"""
from __future__ import annotations

import numpy as np
import pytest

from app.knowledge.coverage.topics import (
    EXAMPLES_PER_CLUSTER,
    MIN_CLUSTER_SIZE,
    _parse_label_response,
    build_topics,
    pick_topic_k,
)


# ─── pick_topic_k 边界 ────────────────────────────────────────────

def test_pick_topic_k_too_small_returns_0():
    assert pick_topic_k(MIN_CLUSTER_SIZE * 3 - 1) == 0


def test_pick_topic_k_typical():
    # sqrt(50/8) ≈ 2.5 → 2
    assert 2 <= pick_topic_k(50) <= 4


def test_pick_topic_k_large_capped():
    assert pick_topic_k(50000) <= 25


# ─── _parse_label_response 容错 ───────────────────────────────────

def test_parse_label_strict_json():
    label, kws = _parse_label_response('{"label": "认证与授权", "keywords": ["OAuth", "JWT"]}')
    assert label == "认证与授权"
    assert kws == ["OAuth", "JWT"]


def test_parse_label_from_code_fence():
    raw = '```json\n{"label": "网络", "keywords": ["TCP"]}\n```'
    label, kws = _parse_label_response(raw)
    assert label == "网络"
    assert kws == ["TCP"]


def test_parse_label_free_text_regex_fallback():
    raw = "好的，我生成了：{\"label\": \"错误排查\", \"keywords\": []}"
    label, kws = _parse_label_response(raw)
    assert label == "错误排查"
    assert kws == []


def test_parse_label_invalid_returns_empty():
    label, kws = _parse_label_response("这不是 JSON")
    assert label == ""
    assert kws == []


def test_parse_label_strips_punctuation_from_keywords():
    label, kws = _parse_label_response('{"label": "x", "keywords": ["a。", "b，"]}')
    assert kws == ["a", "b"]


def test_parse_label_caps_keywords_at_5():
    raw = '{"label": "x", "keywords": ["1","2","3","4","5","6","7"]}'
    _, kws = _parse_label_response(raw)
    assert len(kws) == 5


# ─── build_topics 主流程 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_topics_respects_min_cluster_size():
    # 2 簇 × 2 成员 = 4 chunks；低于 MIN_CLUSTER_SIZE 的簇应被丢弃
    ids = ["a", "b", "c", "d"]
    contents = ["A1", "A2", "B1", "B2"]
    vectors = np.array([
        [1, 0], [1, 0],
        [0, 1], [0, 1],
    ], dtype=np.float32)

    async def label_fn(texts):
        return '{"label": "x", "keywords": []}'

    topics = await build_topics(ids, contents, vectors, label_fn=label_fn, k=2)
    # 每簇 2 < MIN_CLUSTER_SIZE=3 → 返回空
    assert topics == []


@pytest.mark.asyncio
async def test_build_topics_sorted_by_size_desc_and_reindexed():
    # 3 簇 × 不同成员数：6 / 4 / 3
    ids = [f"c{i}" for i in range(13)]
    contents = [f"content {i}" for i in range(13)]
    vectors = np.vstack([
        np.tile(np.array([[1.0, 0.0, 0.0]], dtype=np.float32), (6, 1)),
        np.tile(np.array([[0.0, 1.0, 0.0]], dtype=np.float32), (4, 1)),
        np.tile(np.array([[0.0, 0.0, 1.0]], dtype=np.float32), (3, 1)),
    ])

    async def label_fn(texts):
        return f'{{"label": "topic-{len(texts)}", "keywords": []}}'

    topics = await build_topics(ids, contents, vectors, label_fn=label_fn, k=3)
    assert len(topics) == 3
    assert [t.size for t in topics] == [6, 4, 3]
    assert [t.cluster_id for t in topics] == [0, 1, 2]  # reindexed 0..N
    # example_chunk_ids 数量应 ≤ EXAMPLES_PER_CLUSTER
    assert all(len(t.example_chunk_ids) <= EXAMPLES_PER_CLUSTER for t in topics)


@pytest.mark.asyncio
async def test_build_topics_too_few_chunks_returns_empty():
    ids = ["a", "b"]
    contents = ["x", "y"]
    vectors = np.array([[1.0], [1.0]], dtype=np.float32)

    async def label_fn(texts):
        return ""

    topics = await build_topics(ids, contents, vectors, label_fn=label_fn, k=2)
    assert topics == []


@pytest.mark.asyncio
async def test_build_topics_label_fn_failure_gives_fallback_label():
    ids = [f"c{i}" for i in range(9)]
    contents = [f"x{i}" for i in range(9)]
    vectors = np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (9, 1))

    async def label_fn(texts):
        raise RuntimeError("boom")

    # k=1 不走聚类 → 走 pick_topic_k
    topics = await build_topics(ids, contents, vectors, label_fn=label_fn)
    # 无论聚类结果如何，失败的 label 应被替换成 "话题 N"
    for t in topics:
        assert t.label.startswith("话题 ")


@pytest.mark.asyncio
async def test_build_topics_shape_mismatch_raises():
    async def label_fn(texts):
        return ""

    with pytest.raises(ValueError):
        await build_topics(
            ["a"], ["content", "extra"], np.array([[1.0]], dtype=np.float32),
            label_fn=label_fn,
        )
