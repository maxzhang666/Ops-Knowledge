"""Plan 41 M1.7 — EntrySourcePlugin 纯逻辑回归。"""
from __future__ import annotations

import pytest

from app.knowledge.sources import get_plugin, list_source_types
from app.knowledge.sources.entry import (
    DEFAULT_ENTRY_CHUNK_THRESHOLD,
    EntrySourcePlugin,
    _estimate_tokens,
)


def test_entry_plugin_registered():
    assert "entry" in list_source_types()
    plugin = get_plugin("entry")
    assert isinstance(plugin, EntrySourcePlugin)


def test_entry_capabilities():
    plugin = get_plugin("entry")
    caps = plugin.capabilities
    # 条目型独有：inline_edit + table layout；不挂 folder tree；支持批量导入
    assert caps["supports_inline_edit"] is True
    assert caps["supports_folder_tree"] is False
    assert caps["supports_batch_import"] is True
    assert caps["supports_sync"] is False
    assert caps["ui_layout"] == "table"


def test_default_threshold():
    """spec 41 / spec 01 — 默认 1500 token 触发降级切片"""
    assert DEFAULT_ENTRY_CHUNK_THRESHOLD == 1500


def test_estimate_tokens_chinese():
    """中文 ~1 字 = 1 token；3 字符大致一个 token（中英折中）"""
    assert _estimate_tokens("你好世界") == max(1, 4 // 3)
    # 长文本估算非零
    assert _estimate_tokens("a" * 300) > 50


def test_estimate_tokens_empty():
    """空字符串至少返回 1（避免除零 / 阈值判断异常）"""
    assert _estimate_tokens("") == 1


# ── 降级切片决策表（材质性变化触发重审 + 重切）────────────────────────


def material_changed(
    *,
    old_title: str, old_content: str, old_tags: list | None,
    new_title: str | None, new_content: str | None, new_tags: list | None,
) -> bool:
    """EntrySourcePlugin.update_unit 内的等价纯函数表示。"""
    return (
        (new_title is not None and new_title != old_title)
        or (new_content is not None and new_content != old_content)
        or (new_tags is not None and new_tags != old_tags)
    )


def test_material_change_title_only():
    assert material_changed(
        old_title="A", old_content="x", old_tags=None,
        new_title="B", new_content=None, new_tags=None,
    ) is True


def test_material_change_tags_only():
    """tags 变化也触发重切（tags 注入 chunks.metadata 影响 embedding）"""
    assert material_changed(
        old_title="A", old_content="x", old_tags=["t1"],
        new_title=None, new_content=None, new_tags=["t1", "t2"],
    ) is True


def test_no_change_no_resubmission():
    """无内容变化 → 不触发重切重审"""
    assert material_changed(
        old_title="A", old_content="x", old_tags=["t1"],
        new_title="A", new_content="x", new_tags=["t1"],
    ) is False


def test_partial_update_irrelevant_field():
    """payload 仅传 title 字段且未变 → 不算 material change"""
    assert material_changed(
        old_title="A", old_content="x", old_tags=None,
        new_title="A", new_content=None, new_tags=None,
    ) is False


# ── inline_edit / sync / batch_import 调用路径 ─────────────────────


def test_unsupported_sync_raises():
    """条目型不支持 sync（外部源才有）"""
    import asyncio
    plugin = get_plugin("entry")
    with pytest.raises(NotImplementedError):
        asyncio.run(plugin.sync(None, None))  # type: ignore
