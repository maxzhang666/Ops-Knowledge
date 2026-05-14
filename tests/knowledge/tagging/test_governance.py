"""Spec 25 Plan E — 标签治理统计纯逻辑单测。

mock AsyncSession 隔离 DB；验证：
- get_tag_overview 各指标 SQL 调用 + 计算正确
- accept_ratio 边界：分母为 0 时返 None
- orphan_ratio 边界：total_chunks=0 时返 0.0
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge.tagging.governance import get_tag_overview


def _scalar_session(seq: list) -> MagicMock:
    """构造一个 session.execute(...) 顺序返回 .scalar() 序列的 mock。

    每次 execute 调用 → 返回 mock_result，mock_result.scalar() / .all() 走
    `seq` 列表（按调用顺序消费）。注意：governance code 中 execute 调用既有
    scalar 也有 all，必须按真实顺序排好 seq。
    """
    session = MagicMock()
    call_idx = {"i": 0}

    async def _execute(*_a, **_kw):
        i = call_idx["i"]
        result_value = seq[i]
        call_idx["i"] = i + 1
        result = MagicMock()
        if isinstance(result_value, list):
            result.all = MagicMock(return_value=result_value)
            result.scalar = MagicMock(return_value=0)
        else:
            result.scalar = MagicMock(return_value=result_value)
            result.all = MagicMock(return_value=[])
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


@pytest.mark.asyncio
async def test_get_tag_overview_normal_case():
    """完整数据路径：所有指标都有真实值。

    调用顺序（按 governance.py:get_tag_overview 内 execute 顺序）：
      1. dict_size (scalar) — 10
      2. deprecated_size (scalar) — 2
      3. cloud_rows (.all) — [("退款", 50), ("售后", 30)]
      4. total_chunks (scalar) — 200
      5. orphan_chunks (scalar) — 40
      6. total_entries (scalar) — 100
      7. entries_with_auto (scalar) — 60
      8. action_rows (.all) — [("accept", 80), ("reject", 20)]
      9. retrieval_total (scalar) — 500
      10. routing_used (scalar) — 100
      11. boost_used (scalar) — 200
      12. tag_filter_used (scalar) — 150
    """
    kb_id = uuid.uuid4()
    session = _scalar_session([
        10, 2, [("退款", 50), ("售后", 30)],
        200, 40,
        100, 60,
        [("accept", 80), ("reject", 20)],
        500, 100, 200, 150,
    ])

    out = await get_tag_overview(session, kb_id)
    assert out.dictionary_size == 10
    assert out.deprecated_size == 2
    assert len(out.tag_cloud) == 2
    assert out.tag_cloud[0].canonical == "退款"
    assert out.tag_cloud[0].usage_count == 50

    assert out.total_chunks == 200
    assert out.orphan_chunks == 40
    assert out.orphan_ratio == pytest.approx(0.2)

    assert out.total_entries == 100
    assert out.entries_with_auto_tags == 60

    assert out.accept_count_30d == 80
    assert out.reject_count_30d == 20
    assert out.accept_ratio_30d == pytest.approx(0.8)

    assert out.retrieval_total_30d == 500
    assert out.routing_used_30d == 100
    assert out.boost_used_30d == 200
    assert out.tag_filter_used_30d == 150


@pytest.mark.asyncio
async def test_get_tag_overview_empty_kb():
    """新 KB / 无数据：所有指标安全返 0 / None。"""
    kb_id = uuid.uuid4()
    session = _scalar_session([
        0, 0, [],
        0, 0,
        0, 0,
        [],
        0, 0, 0, 0,
    ])

    out = await get_tag_overview(session, kb_id)
    assert out.dictionary_size == 0
    assert out.tag_cloud == []
    assert out.total_chunks == 0
    assert out.orphan_chunks == 0
    assert out.orphan_ratio == 0.0  # 防止 0 / 0
    assert out.total_entries == 0
    assert out.entries_with_auto_tags == 0
    # 接受率分母为 0 → 返 None（前端可显示 "—"）
    assert out.accept_count_30d == 0
    assert out.reject_count_30d == 0
    assert out.accept_ratio_30d is None
    assert out.retrieval_total_30d == 0


@pytest.mark.asyncio
async def test_get_tag_overview_only_rejects():
    """只有 reject 没有 accept → 接受率 0%（不是 None）。"""
    kb_id = uuid.uuid4()
    session = _scalar_session([
        5, 0, [],
        10, 0,
        5, 0,
        [("reject", 10)],
        0, 0, 0, 0,
    ])

    out = await get_tag_overview(session, kb_id)
    assert out.accept_count_30d == 0
    assert out.reject_count_30d == 10
    assert out.accept_ratio_30d == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_get_tag_overview_orphan_ratio_high():
    """高孤儿比例：100 chunks 中 80 个无 tag。"""
    kb_id = uuid.uuid4()
    session = _scalar_session([
        3, 0, [("a", 1)],
        100, 80,
        50, 0,
        [],
        0, 0, 0, 0,
    ])

    out = await get_tag_overview(session, kb_id)
    assert out.orphan_chunks == 80
    assert out.orphan_ratio == pytest.approx(0.8)
