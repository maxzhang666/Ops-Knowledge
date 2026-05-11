"""IngestionPlugin 注册表 — Plan 40 M1.3。

借鉴 app/auth/providers/registry.py 模式（不重新发明 plugin 框架）。
Plugin 在模块 import 时调 register_plugin(); main.py 启动时 import sources/
触发所有 plugin 注册。
"""
from __future__ import annotations

from app.knowledge.sources.base import IngestionPlugin

# 全局注册表 —— source_type → plugin 实例
SOURCE_PLUGINS: dict[str, IngestionPlugin] = {}


def register_plugin(plugin: IngestionPlugin) -> None:
    """注册一个 IngestionPlugin。重复注册同 source_type 抛异常（防止配置冲突）。"""
    if plugin.source_type in SOURCE_PLUGINS:
        raise ValueError(
            f"duplicate IngestionPlugin source_type: {plugin.source_type}",
        )
    SOURCE_PLUGINS[plugin.source_type] = plugin


def get_plugin(source_type: str) -> IngestionPlugin:
    """按 source_type 取 plugin。未注册抛 ValueError。"""
    if source_type not in SOURCE_PLUGINS:
        raise ValueError(f"unknown source_type: {source_type}")
    return SOURCE_PLUGINS[source_type]


def list_source_types() -> list[str]:
    """已注册的 source_type 列表，前端 KB 创建 dialog 用。"""
    return sorted(SOURCE_PLUGINS.keys())


def is_supported(source_type: str) -> bool:
    return source_type in SOURCE_PLUGINS
