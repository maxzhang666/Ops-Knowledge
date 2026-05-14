"""Spec 25 Plan D — LLM query routing 纯逻辑单测。

mock AsyncSession + ModelService 隔离 DB / LLM 调用，验证：
- 关闭 / 未配 LLM 时返 []
- 字典为空时返 []
- LLM 输出 JSON 数组的解析与去重
- LLM 幻觉（不在字典中的 tag）被过滤
- LLM 调用失败完全静默
- max_n 截断
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge.tagging.query_router import _extract_json_array, route_query_to_tags


# ── _extract_json_array ──────────────────────────────────────────


def test_extract_json_array_clean_input():
    assert _extract_json_array('["a", "b"]') == ["a", "b"]


def test_extract_json_array_with_preamble():
    raw = '我推荐这些标签：\n```json\n["退款", "售后"]\n```'
    assert _extract_json_array(raw) == ["退款", "售后"]


def test_extract_json_array_empty_array():
    assert _extract_json_array("[]") == []


def test_extract_json_array_garbage():
    assert _extract_json_array("not json") == []
    assert _extract_json_array("") == []


def test_extract_json_array_non_list():
    """LLM 返回 dict 等非 list → 返 []。"""
    assert _extract_json_array('{"tag": "x"}') == []


# ── route_query_to_tags fixtures ─────────────────────────────────


def _make_settings(*, enabled: bool, llm_id: object | None) -> MagicMock:
    s = MagicMock()
    s.tag_routing_enabled = enabled
    s.auto_tag_llm_model_id = llm_id
    return s


def _make_session(
    *, settings_row: MagicMock | None, dict_rows: list[tuple[str, int]],
) -> MagicMock:
    """构造一个 AsyncSession mock：db.get → settings_row；db.execute(select TagDictionary) → dict_rows。"""
    session = MagicMock()
    session.get = AsyncMock(return_value=settings_row)
    exec_result = MagicMock()
    exec_result.all = MagicMock(return_value=dict_rows)
    session.execute = AsyncMock(return_value=exec_result)
    return session


# ── route_query_to_tags 各路径 ───────────────────────────────────


@pytest.mark.asyncio
async def test_routing_disabled_returns_empty():
    session = _make_session(
        settings_row=_make_settings(enabled=False, llm_id="x"),
        dict_rows=[],
    )
    out = await route_query_to_tags(session, "kb1", "退款", MagicMock())
    assert out == []


@pytest.mark.asyncio
async def test_routing_no_settings_returns_empty():
    session = _make_session(settings_row=None, dict_rows=[])
    out = await route_query_to_tags(session, "kb1", "退款", MagicMock())
    assert out == []


@pytest.mark.asyncio
async def test_routing_no_llm_model_returns_empty():
    session = _make_session(
        settings_row=_make_settings(enabled=True, llm_id=None),
        dict_rows=[("退款", 10)],
    )
    out = await route_query_to_tags(session, "kb1", "退款", MagicMock())
    assert out == []


@pytest.mark.asyncio
async def test_routing_empty_dict_returns_empty():
    """字典空 → 没有 candidate canonical，跳过 LLM 调用。"""
    model_svc = MagicMock()
    model_svc.chat_by_registry = AsyncMock()
    session = _make_session(
        settings_row=_make_settings(enabled=True, llm_id="llm-id"),
        dict_rows=[],
    )
    out = await route_query_to_tags(session, "kb1", "退款", model_svc)
    assert out == []
    model_svc.chat_by_registry.assert_not_called()


@pytest.mark.asyncio
async def test_routing_returns_canonicals_in_dict():
    model_svc = MagicMock()
    model_svc.chat_by_registry = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps(["退款", "售后"])}}],
    })
    session = _make_session(
        settings_row=_make_settings(enabled=True, llm_id="llm-id"),
        dict_rows=[("退款", 10), ("售后", 5), ("营销", 2)],
    )
    out = await route_query_to_tags(session, "kb1", "想退钱", model_svc)
    assert out == ["退款", "售后"]


@pytest.mark.asyncio
async def test_routing_filters_hallucinated_tags():
    """LLM 返回的不在字典中的 canonical 被过滤。"""
    model_svc = MagicMock()
    model_svc.chat_by_registry = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps([
            "退款", "我编的tag", "售后",
        ])}}],
    })
    session = _make_session(
        settings_row=_make_settings(enabled=True, llm_id="llm-id"),
        dict_rows=[("退款", 10), ("售后", 5)],
    )
    out = await route_query_to_tags(session, "kb1", "x", model_svc)
    assert out == ["退款", "售后"]


@pytest.mark.asyncio
async def test_routing_dedups_repeated_tags():
    model_svc = MagicMock()
    model_svc.chat_by_registry = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps([
            "退款", "退款", "售后",
        ])}}],
    })
    session = _make_session(
        settings_row=_make_settings(enabled=True, llm_id="llm-id"),
        dict_rows=[("退款", 10), ("售后", 5)],
    )
    out = await route_query_to_tags(session, "kb1", "x", model_svc)
    assert out == ["退款", "售后"]


@pytest.mark.asyncio
async def test_routing_respects_max_n():
    """LLM 返回多个，路由按 max_n 截断。"""
    model_svc = MagicMock()
    model_svc.chat_by_registry = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps([
            "t1", "t2", "t3", "t4", "t5", "t6",
        ])}}],
    })
    session = _make_session(
        settings_row=_make_settings(enabled=True, llm_id="llm-id"),
        dict_rows=[(f"t{i}", 1) for i in range(1, 7)],
    )
    out = await route_query_to_tags(session, "kb1", "x", model_svc, max_n=3)
    assert out == ["t1", "t2", "t3"]


@pytest.mark.asyncio
async def test_routing_llm_failure_returns_empty():
    """LLM 调用抛异常 → 返 []，不阻塞主路径。"""
    model_svc = MagicMock()
    model_svc.chat_by_registry = AsyncMock(side_effect=RuntimeError("upstream"))
    session = _make_session(
        settings_row=_make_settings(enabled=True, llm_id="llm-id"),
        dict_rows=[("退款", 10)],
    )
    out = await route_query_to_tags(session, "kb1", "x", model_svc)
    assert out == []


@pytest.mark.asyncio
async def test_routing_garbage_response_returns_empty():
    """LLM 返回非 JSON → 返 []。"""
    model_svc = MagicMock()
    model_svc.chat_by_registry = AsyncMock(return_value={
        "choices": [{"message": {"content": "我觉得相关的是退款"}}],
    })
    session = _make_session(
        settings_row=_make_settings(enabled=True, llm_id="llm-id"),
        dict_rows=[("退款", 10)],
    )
    out = await route_query_to_tags(session, "kb1", "x", model_svc)
    assert out == []


@pytest.mark.asyncio
async def test_routing_skips_non_string_items():
    """LLM 输出混入非 string（dict / null）→ 跳过。"""
    model_svc = MagicMock()
    model_svc.chat_by_registry = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps([
            "退款", None, {"tag": "x"}, "售后",
        ])}}],
    })
    session = _make_session(
        settings_row=_make_settings(enabled=True, llm_id="llm-id"),
        dict_rows=[("退款", 10), ("售后", 5)],
    )
    out = await route_query_to_tags(session, "kb1", "x", model_svc)
    assert out == ["退款", "售后"]
