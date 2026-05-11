"""Milvus 治理纯逻辑单测：避免触碰真实 Milvus / DB，用 monkeypatch 隔离。"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.knowledge.milvus.governance import _extract_collection_dim
from app.knowledge.milvus import governance_tasks


def test_extract_dim_from_describe():
    """describe_collection 返回的 schema 中找 FLOAT_VECTOR 字段的 dim。"""
    desc = {
        "fields": [
            {"name": "id", "params": {}},
            {"name": "vector", "params": {"dim": 1536}},
            {"name": "content", "params": {}},
        ]
    }
    assert _extract_collection_dim(desc) == 1536


def test_extract_dim_no_vector_field():
    desc = {"fields": [{"name": "id", "params": {}}]}
    assert _extract_collection_dim(desc) is None


def test_extract_dim_none_input():
    assert _extract_collection_dim(None) is None
    assert _extract_collection_dim({}) is None


def test_extract_dim_invalid_value_skipped():
    desc = {"fields": [{"name": "vector", "params": {"dim": "not_int"}}]}
    assert _extract_collection_dim(desc) is None


def test_compute_orphans_no_collection(monkeypatch):
    """collection 不存在时返回空孤儿 + collection_exists=False。"""
    milvus = MagicMock()
    milvus.collection_exists.return_value = False
    result = governance_tasks._compute_orphans(str(uuid.uuid4()), milvus)
    assert result["collection_exists"] is False
    assert result["orphan_ids"] == []
    assert result["milvus_count"] == 0
    assert result["pg_count"] == 0


def test_compute_orphans_set_diff_logic(monkeypatch):
    """milvus 有 [a, b, c]，PG 有 [b, c, d] → 孤儿 = [a]，PG 多了 d 但不算。"""
    kb_id = str(uuid.uuid4())
    a_id = str(uuid.uuid4())
    b_id = str(uuid.uuid4())
    c_id = str(uuid.uuid4())
    d_id = str(uuid.uuid4())

    milvus = MagicMock()
    milvus.collection_exists.return_value = True
    milvus.list_ids.return_value = [a_id, b_id, c_id]

    # mock PG session
    fake_session = MagicMock()
    fake_session.execute.return_value.all.return_value = [
        (uuid.UUID(b_id),), (uuid.UUID(c_id),), (uuid.UUID(d_id),),
    ]

    class _SessCtx:
        def __enter__(self):
            return fake_session
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(governance_tasks, "_get_sync_engine", lambda: None)
    monkeypatch.setattr(governance_tasks, "Session", lambda _engine: _SessCtx())

    result = governance_tasks._compute_orphans(kb_id, milvus)
    assert result["collection_exists"] is True
    assert result["milvus_count"] == 3
    assert result["pg_count"] == 3
    assert result["orphan_ids"] == [a_id]


def test_acquire_lock_falls_through_when_redis_down(monkeypatch):
    """redis 不可用时 _acquire_lock 返回 True（任务幂等可重跑，不阻塞）。"""
    def _broken(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(governance_tasks.redis, "from_url", _broken)
    assert governance_tasks._acquire_lock("any-kb") is True


def test_release_lock_silent_on_failure(monkeypatch):
    """release_lock 永远不抛异常（即使 redis 挂）。"""
    def _broken(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(governance_tasks.redis, "from_url", _broken)
    governance_tasks._release_lock("any-kb")  # no exception
