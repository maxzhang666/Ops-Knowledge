"""Spec 25 §2.6 — KB 级标签功能配置 + preset。

不引入 KB.tag_config JSONB 混乱 —— 独立表 kb_tag_settings 一对一 KB。
preset 提供三档预设值（low_cost / balanced / high_quality），单字段改动
自动落档 preset='custom' 标记用户已偏离。
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.knowledge.service import KBService
from app.knowledge.tagging.models import KBTagSettings

logger = structlog.get_logger(__name__)


# ── Preset 表（service 层硬编码，不暴露 user UI 修改）────────────


PRESET_VALUES: dict[str, dict] = {
    "low_cost": {
        "auto_tag_provider": "keybert",
        "auto_tag_max_per_unit": 3,
        "auto_tag_confidence_threshold": 0.7,
        "tag_boost_weight": 0.03,
        "tag_routing_enabled": False,
    },
    "balanced": {
        "auto_tag_provider": "hybrid",
        "auto_tag_max_per_unit": 5,
        "auto_tag_confidence_threshold": 0.6,
        "tag_boost_weight": 0.05,
        "tag_routing_enabled": False,
    },
    "high_quality": {
        "auto_tag_provider": "llm",
        "auto_tag_max_per_unit": 8,
        "auto_tag_confidence_threshold": 0.5,
        "tag_boost_weight": 0.08,
        "tag_routing_enabled": True,
    },
}


class KBTagSettingsService:
    """KB 维度的标签配置 CRUD + preset 切换。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_default(self, kb_id: uuid.UUID) -> KBTagSettings:
        """KB 创建时调用：插入 balanced preset 默认行；幂等。"""
        existing = await self.db.get(KBTagSettings, kb_id)
        if existing is not None:
            return existing
        row = KBTagSettings(kb_id=kb_id, preset="balanced")
        # balanced 的具体字段由 PRESET_VALUES 提供
        for k, v in PRESET_VALUES["balanced"].items():
            setattr(row, k, v)
        self.db.add(row)
        await self.db.flush()
        return row

    async def apply_preset(
        self, kb_id: uuid.UUID, preset: str,
    ) -> KBTagSettings:
        if preset not in PRESET_VALUES:
            raise ValueError(f"Unknown preset: {preset}")
        row = await self.get_or_create_default(kb_id)
        row.preset = preset
        for k, v in PRESET_VALUES[preset].items():
            setattr(row, k, v)
        await self.db.flush()
        return row

    async def update_fields(
        self, kb_id: uuid.UUID, updates: dict,
    ) -> KBTagSettings:
        """字段级 patch；任何修改自动标记 preset='custom'。"""
        row = await self.get_or_create_default(kb_id)
        # 允许更新字段白名单
        allowed = {
            "auto_tag_enabled", "auto_tag_provider", "auto_tag_llm_model_id",
            "auto_tag_max_per_unit", "auto_tag_confidence_threshold",
            "tag_filter_enabled", "tag_boost_weight", "tag_routing_enabled",
        }
        touched = False
        for k, v in updates.items():
            if k not in allowed:
                continue
            if getattr(row, k) != v:
                setattr(row, k, v)
                touched = True
        if touched:
            row.preset = "custom"
        await self.db.flush()
        return row


# ── Router ───────────────────────────────────────────────────────


router = APIRouter(
    prefix="/knowledge/{kb_id}/tag-settings",
    tags=["tag-settings"],
)


class KBTagSettingsResponse(BaseModel):
    kb_id: uuid.UUID
    preset: str
    auto_tag_enabled: bool
    auto_tag_provider: str
    auto_tag_llm_model_id: uuid.UUID | None
    auto_tag_max_per_unit: int
    auto_tag_confidence_threshold: float
    tag_filter_enabled: bool
    tag_boost_weight: float
    tag_routing_enabled: bool

    model_config = {"from_attributes": True}


class UpdateSettingsBody(BaseModel):
    preset: str | None = Field(None, description="切档预设：low_cost/balanced/high_quality")
    auto_tag_enabled: bool | None = None
    auto_tag_provider: str | None = None
    auto_tag_llm_model_id: uuid.UUID | None = None
    auto_tag_max_per_unit: int | None = Field(None, ge=1, le=20)
    auto_tag_confidence_threshold: float | None = Field(None, ge=0.0, le=1.0)
    tag_filter_enabled: bool | None = None
    tag_boost_weight: float | None = Field(None, ge=0.0, le=1.0)
    tag_routing_enabled: bool | None = None


@router.get("", response_model=KBTagSettingsResponse)
async def get_settings(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await KBService(db).get_kb(kb_id)
    await check_resource_access(
        current_user, "knowledge_base", kb.id, db, kb.created_by, "view",
    )
    svc = KBTagSettingsService(db)
    row = await svc.get_or_create_default(kb_id)
    await db.commit()
    return KBTagSettingsResponse.model_validate(row)


@router.post("/update", response_model=KBTagSettingsResponse)
async def update_settings(
    kb_id: uuid.UUID,
    body: UpdateSettingsBody,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await KBService(db).get_kb(kb_id)
    await check_resource_access(
        current_user, "knowledge_base", kb.id, db, kb.created_by, "edit",
    )
    svc = KBTagSettingsService(db)
    # preset 与字段更新互斥优先级：preset 在前；preset 切换后单字段 patch 再覆盖
    if body.preset is not None:
        try:
            await svc.apply_preset(kb_id, body.preset)
        except ValueError as e:
            raise HTTPException(400, str(e))
    field_updates = {
        k: v for k, v in body.model_dump(exclude_unset=True).items()
        if k != "preset" and v is not None
    }
    if field_updates:
        await svc.update_fields(kb_id, field_updates)
    await db.commit()
    row = await svc.get_or_create_default(kb_id)
    return KBTagSettingsResponse.model_validate(row)
