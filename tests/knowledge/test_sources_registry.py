"""Plan 40 M1 — IngestionPlugin 注册表 + capabilities 纯逻辑测试。"""
from __future__ import annotations

import pytest

from app.knowledge.sources import (
    SOURCE_PLUGINS,
    get_plugin,
    is_supported,
    list_source_types,
)
from app.knowledge.sources.base import IngestionPlugin


def test_file_source_registered():
    assert "file" in SOURCE_PLUGINS
    plugin = get_plugin("file")
    assert plugin.source_type == "file"
    assert isinstance(plugin, IngestionPlugin)


def test_file_capabilities():
    plugin = get_plugin("file")
    caps = plugin.capabilities
    # 文件型独有：folder_tree + batch_import；不支持 inline_edit / sync
    assert caps["supports_folder_tree"] is True
    assert caps["supports_batch_import"] is True
    assert caps["supports_inline_edit"] is False
    assert caps["supports_sync"] is False
    assert caps["ui_layout"] == "folder_tree"


def test_unknown_source_raises():
    with pytest.raises(ValueError, match="unknown source_type"):
        get_plugin("nonexistent_xyz")


def test_is_supported():
    assert is_supported("file") is True
    assert is_supported("entry") is True  # Plan 41 已解锁
    assert is_supported("git_repo") is False  # 未来 roadmap


def test_list_source_types_sorted():
    types = list_source_types()
    assert "file" in types
    assert types == sorted(types)


def test_inline_edit_raises_when_not_supported():
    """文件型 plugin 不支持 inline edit；调用应抛 NotImplementedError。"""
    import asyncio
    plugin = get_plugin("file")
    with pytest.raises(NotImplementedError):
        asyncio.run(plugin.create_unit(None, None, {}))  # type: ignore
    with pytest.raises(NotImplementedError):
        asyncio.run(plugin.update_unit(None, None, {}))  # type: ignore
    with pytest.raises(NotImplementedError):
        asyncio.run(plugin.sync(None, None))  # type: ignore
