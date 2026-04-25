"""Governance API (Plan 32 M2.4)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access, require_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.core.exceptions import AppError
from app.knowledge.governance.schemas import (
    DEFAULT_WEIGHTS,
    GovernanceHealthResponse,
    GovernanceOverview,
    GovernanceWeights,
    KBGovernanceConfig,
)
from app.knowledge.governance.service import GovernanceService
from app.knowledge.models import KnowledgeBase

router = APIRouter(prefix="/knowledge", tags=["governance"])


async def _load_weights(db: AsyncSession) -> GovernanceWeights:
    """Read SystemSettings.governance_weights with fallback to defaults."""
    try:
        from app.system.models import SystemSettings
        row = await db.get(SystemSettings, 1)
        cfg = (row.settings or {}) if row else {}
        raw = cfg.get("governance_weights")
        if raw:
            return GovernanceWeights.model_validate(raw)
    except Exception:
        pass
    return GovernanceWeights(**DEFAULT_WEIGHTS)


@router.get("/governance/overview", response_model=GovernanceOverview)
async def governance_overview(
    _admin: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """Admin cross-KB view — one health card per KB."""
    weights = await _load_weights(db)
    svc = GovernanceService(db)
    return await svc.compute_overview(weights)


@router.get("/{kb_id}/governance", response_model=GovernanceHealthResponse)
async def kb_governance(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)
    weights = await _load_weights(db)
    svc = GovernanceService(db)
    try:
        return await svc.compute_health(kb_id, weights)
    except AppError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/{kb_id}/governance/config", response_model=KBGovernanceConfig)
async def update_kb_governance_config(
    kb_id: uuid.UUID,
    cfg: KBGovernanceConfig,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(
        current_user, "knowledge_base", kb.id, db, kb.created_by, required_level="edit",
    )
    kb.governance_config = cfg.model_dump()
    await db.flush()
    return cfg
