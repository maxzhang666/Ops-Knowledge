"""Orchestrator Agent rule + config + audit endpoints.

Permission: agent owner OR system_admin OR dept_admin of the Agent's
department. Regular users can GET rules (UI rendering) but can't mutate
or read diagnostic data.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import Agent
from app.agent.orchestrator.models import AgentRule, OrchestratorTrace
from app.agent.orchestrator.schemas import (
    AgentRuleCreate,
    AgentRuleMove,
    AgentRuleResponse,
    AgentRuleUpdate,
    ClassifierTestRequest,
    ClassifierTestResult,
    OrchestratorConfig,
    OrchestratorTraceResponse,
    RuleMetrics,
)
from app.agent.orchestrator.service import OrchestratorService
from app.agent.service import AgentService
from app.auth.dependencies import CurrentUser, check_resource_access
from app.auth.models import UserRole
from app.core.database import get_db
from app.core.exceptions import AppError

router = APIRouter(prefix="/agents/{agent_id}", tags=["orchestrator"])


# ── Authorization helpers ────────────────────────────────────────

async def _assert_can_manage(
    agent_id: uuid.UUID, current_user, db: AsyncSession,
) -> Agent:
    """Require "edit" level on the Agent — that's the existing semantics
    for owner / system_admin / dept_admin with edit share. Rule mutation
    and trace viewing reuse this gate.
    """
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    await check_resource_access(
        current_user, "agent", agent.id, db, agent.created_by, required_level="edit",
    )
    return agent


# ── Rules CRUD ───────────────────────────────────────────────────

@router.get("/rules", response_model=list[AgentRuleResponse])
async def list_rules(
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = OrchestratorService(db)
    return await svc.list_rules(agent_id)


@router.post("/rules", response_model=AgentRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    agent_id: uuid.UUID,
    data: AgentRuleCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_can_manage(agent_id, current_user, db)
    svc = OrchestratorService(db)
    try:
        return await svc.create_rule(agent_id, data, created_by=current_user.id)
    except AppError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/rules/{rule_id}/update", response_model=AgentRuleResponse)
async def update_rule(
    agent_id: uuid.UUID,
    rule_id: uuid.UUID,
    data: AgentRuleUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_can_manage(agent_id, current_user, db)
    svc = OrchestratorService(db)
    try:
        return await svc.update_rule(agent_id, rule_id, data)
    except AppError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/rules/{rule_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    agent_id: uuid.UUID,
    rule_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_can_manage(agent_id, current_user, db)
    svc = OrchestratorService(db)
    try:
        await svc.delete_rule(agent_id, rule_id)
    except AppError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/rules/{rule_id}/move", response_model=AgentRuleResponse)
async def move_rule(
    agent_id: uuid.UUID,
    rule_id: uuid.UUID,
    data: AgentRuleMove,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_can_manage(agent_id, current_user, db)
    svc = OrchestratorService(db)
    try:
        return await svc.move_rule(agent_id, rule_id, data)
    except AppError as e:
        raise HTTPException(e.status_code, e.message)


# ── Orchestrator config ──────────────────────────────────────────

@router.post("/orchestrator-config/update")
async def update_config(
    agent_id: uuid.UUID,
    cfg: OrchestratorConfig,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_can_manage(agent_id, current_user, db)
    svc = OrchestratorService(db)
    try:
        return await svc.update_config(agent_id, cfg)
    except AppError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/classifier/test", response_model=ClassifierTestResult)
async def test_classifier(
    agent_id: uuid.UUID,
    body: ClassifierTestRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_can_manage(agent_id, current_user, db)
    svc = OrchestratorService(db)
    try:
        return await svc.test_classifier(agent_id, body.message)
    except AppError as e:
        raise HTTPException(e.status_code, e.message)


# ── Audit / metrics ──────────────────────────────────────────────

@router.get("/traces", response_model=list[OrchestratorTraceResponse])
async def list_traces(
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    await _assert_can_manage(agent_id, current_user, db)
    limit = max(1, min(limit, 500))
    rows = (await db.execute(
        select(OrchestratorTrace)
        .where(OrchestratorTrace.agent_id == agent_id)
        .order_by(desc(OrchestratorTrace.created_at))
        .limit(limit)
    )).scalars().all()
    return list(rows)


@router.get("/rules/metrics", response_model=list[RuleMetrics])
async def rules_metrics(
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_can_manage(agent_id, current_user, db)
    rows = (await db.execute(
        select(AgentRule).where(AgentRule.agent_id == agent_id)
    )).scalars().all()
    return [
        RuleMetrics(
            rule_id=r.id,
            hit_count=r.hit_count,
            last_hit_at=r.last_hit_at,
            avg_latency_ms=r.avg_latency_ms,
        )
        for r in rows
    ]
