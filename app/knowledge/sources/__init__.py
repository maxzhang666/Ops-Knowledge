"""IngestionPlugin 框架 — Plan 40。

import sources/ 触发所有具体 plugin 模块的 register_plugin() 调用。
新增 plugin 只需在 plugins 元组中加一项，不需要改任何注册逻辑。
"""
from app.knowledge.sources import file as _file_plugin  # noqa: F401
from app.knowledge.sources import entry as _entry_plugin  # noqa: F401
from app.knowledge.sources.base import (
    ChunkSeed,
    IngestionPlugin,
    PluginCapabilities,
    UnitView,
)
from app.knowledge.sources.registry import (
    SOURCE_PLUGINS,
    get_plugin,
    is_supported,
    list_source_types,
    register_plugin,
)


def list_sources_capabilities() -> list[dict]:
    """返回所有已注册 plugin 的 source_type + capabilities，供前端动态渲染
    KB 创建 dialog / 详情 tabs 等。加新 plugin 自动出现在前端选项中。"""
    return [
        {"source_type": st, "capabilities": dict(p.capabilities)}
        for st, p in sorted(SOURCE_PLUGINS.items())
    ]


__all__ = [
    "ChunkSeed",
    "IngestionPlugin",
    "PluginCapabilities",
    "SOURCE_PLUGINS",
    "UnitView",
    "get_plugin",
    "is_supported",
    "list_source_types",
    "list_sources_capabilities",
    "register_plugin",
]
