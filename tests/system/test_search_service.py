"""Plan 34 M4 — SearchService dataclass + short-circuit tests."""
from __future__ import annotations

import asyncio
import uuid

from app.system.search_service import SearchHit, SearchService


class _StubDB:
    """足够小的 stub 让 search() 的 short-circuit 路径走通。"""
    async def execute(self, *args, **kwargs):  # noqa: D401, ARG002
        raise AssertionError("DB should not be hit when query is too short")


def test_search_hit_dataclass():
    h = SearchHit(kind="kb", id="x", title="t", subtitle="s", href="/x")
    assert h.kind == "kb"
    assert h.title == "t"
    assert h.href == "/x"


def test_search_short_query_short_circuits_no_db():
    """少于 2 字符的 query 必须不触达 DB（性能 + 噪声防护）。"""
    svc = SearchService(_StubDB())  # type: ignore[arg-type]

    async def run() -> dict:
        return await svc.search("a", user_id=uuid.uuid4())

    out = asyncio.run(run())
    assert out == {"kbs": [], "documents": [], "conversations": []}


def test_search_empty_query_short_circuits():
    svc = SearchService(_StubDB())  # type: ignore[arg-type]

    async def run() -> dict:
        return await svc.search("", user_id=uuid.uuid4())

    out = asyncio.run(run())
    assert out == {"kbs": [], "documents": [], "conversations": []}


def test_search_whitespace_only_short_circuits():
    svc = SearchService(_StubDB())  # type: ignore[arg-type]

    async def run() -> dict:
        return await svc.search("   ", user_id=uuid.uuid4())

    out = asyncio.run(run())
    assert out["kbs"] == []
