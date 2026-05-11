"""Plan 41 P19 — IngestionPlugin 元数据 endpoint。

让前端动态拉取已注册 plugin + capabilities，避免硬编码 source_type 枚举。
加新 plugin 仅需后端注册，前端自动可见。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.knowledge.sources import list_sources_capabilities

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
async def list_sources() -> list[dict]:
    """返回 [{source_type, capabilities}] —— 已注册的 IngestionPlugin。
    capabilities 含 supports_inline_edit / supports_folder_tree /
    supports_sync / supports_batch_import / ui_layout，供前端按 plugin
    能力动态渲染管理 UI。"""
    return list_sources_capabilities()
