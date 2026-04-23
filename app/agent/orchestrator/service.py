"""OrchestratorService — rule CRUD + ``route()`` main entry.

``route()`` is the single thing chat/orchestrator_pipeline calls; it
composes engine.evaluate + dispatcher + audit.record_trace. Owns the
``on_handler_error`` state machine: ``fallback_next`` re-enters the
cascade skipping the failed rule; ``use_default`` jumps straight to
the configured default_handler; ``return_error`` surfaces to user.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import Agent
from app.agent.orchestrator import audit, engine
from app.agent.orchestrator.adapters import DispatchContext
from app.agent.orchestrator.dispatcher import dispatch_default, dispatch_matched
from app.agent.orchestrator.events import OrchestratorEvent
from app.agent.orchestrator.matchers.base import MatchInput
from app.agent.orchestrator.matchers.llm_intent import classify
from app.agent.orchestrator.metadata import assert_path_trusted, build_metadata
from app.agent.orchestrator.models import AgentRule
from app.agent.orchestrator.schemas import (
    DEFAULT_DIAG_ROLES,
    DEFAULT_TRUSTED_PATHS,
    AgentRuleCreate,
    AgentRuleMove,
    AgentRuleUpdate,
    ClassifierTestResult,
    OrchestratorConfig,
)
from app.core.database import async_session
from app.core.exceptions import NotFoundError, ValidationError

logger = structlog.get_logger(__name__)

PRIORITY_STEP = 10.0  # default spacing when appending to end


class OrchestratorService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Rule CRUD ────────────────────────────────────────────────

    async def list_rules(self, agent_id: uuid.UUID) -> list[AgentRule]:
        stmt = (
            select(AgentRule)
            .where(AgentRule.agent_id == agent_id)
            .order_by(AgentRule.priority.asc(), AgentRule.created_at.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)

    async def create_rule(
        self, agent_id: uuid.UUID, data: AgentRuleCreate, created_by: uuid.UUID,
    ) -> AgentRule:
        await self._assert_agent_is_orchestrator(agent_id)
        await self._validate_rule_against_agent(agent_id, data)

        priority = data.priority
        if priority is None:
            # Append to end
            max_prio = (await self.db.execute(
                select(AgentRule.priority)
                .where(AgentRule.agent_id == agent_id)
                .order_by(AgentRule.priority.desc()).limit(1)
            )).scalar()
            priority = (max_prio or 0.0) + PRIORITY_STEP

        rule = AgentRule(
            agent_id=agent_id,
            priority=priority,
            is_active=data.is_active,
            match_type=data.match_type,
            match_config=data.match_config,
            handler_type=data.handler_type,
            handler_id=data.handler_id,
            handler_config=data.handler_config,
            on_handler_error=data.on_handler_error,
            created_by=created_by,
        )
        self.db.add(rule)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def update_rule(
        self, agent_id: uuid.UUID, rule_id: uuid.UUID, data: AgentRuleUpdate,
    ) -> AgentRule:
        rule = await self._get_rule(agent_id, rule_id)
        payload = data.model_dump(exclude_unset=True)

        # Re-validate combined new state against Agent config (trusted paths,
        # classifier categories) — a rule that was valid may become invalid
        # if admin tightens trusted_metadata_paths between edits.
        if "match_type" in payload or "match_config" in payload:
            final_type = payload.get("match_type", rule.match_type)
            final_config = payload.get("match_config", rule.match_config)
            await self._check_match_against_agent(agent_id, final_type, final_config)

        for k, v in payload.items():
            setattr(rule, k, v)
        rule.version = (rule.version or 1) + 1
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def delete_rule(self, agent_id: uuid.UUID, rule_id: uuid.UUID) -> None:
        rule = await self._get_rule(agent_id, rule_id)
        await self.db.delete(rule)
        await self.db.flush()

    async def move_rule(
        self, agent_id: uuid.UUID, rule_id: uuid.UUID, move: AgentRuleMove,
    ) -> AgentRule:
        """Compute midpoint priority between ``after_rule_id`` and the
        rule following it. after_rule_id=null ⇒ move to top (priority =
        min/2)."""
        rule = await self._get_rule(agent_id, rule_id)

        # Current ordering without the moved rule
        stmt = (
            select(AgentRule)
            .where(AgentRule.agent_id == agent_id, AgentRule.id != rule_id)
            .order_by(AgentRule.priority.asc())
        )
        others = (await self.db.execute(stmt)).scalars().all()

        if move.after_rule_id is None:
            # Move to top: half the current minimum (or STEP if list empty)
            new_prio = (others[0].priority / 2.0) if others else PRIORITY_STEP
        else:
            # Find after_rule and its following neighbor
            idx = next((i for i, r in enumerate(others) if r.id == move.after_rule_id), None)
            if idx is None:
                raise ValidationError(f"after_rule_id {move.after_rule_id} not in this agent's rules")
            before = others[idx]
            after = others[idx + 1] if idx + 1 < len(others) else None
            if after is None:
                new_prio = before.priority + PRIORITY_STEP
            else:
                new_prio = (before.priority + after.priority) / 2.0

        rule.priority = new_prio
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    # ── Agent config ─────────────────────────────────────────────

    async def update_config(self, agent_id: uuid.UUID, cfg: OrchestratorConfig) -> dict:
        agent = await self.db.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError("Agent", str(agent_id))
        agent.orchestrator_config = cfg.model_dump(exclude_none=False, mode="json")
        await self.db.flush()
        return agent.orchestrator_config

    async def test_classifier(
        self, agent_id: uuid.UUID, message: str,
    ) -> ClassifierTestResult:
        agent = await self.db.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError("Agent", str(agent_id))
        classifier_cfg = (agent.orchestrator_config or {}).get("classifier")
        if not classifier_cfg:
            raise ValidationError("Agent has no classifier configured")
        out = await classify(
            agent_id=agent_id,
            message=message,
            classifier_cfg=classifier_cfg,
            db_factory=async_session,
        )
        if out is None:
            return ClassifierTestResult(category="__unknown__", confidence=0.0, cached=False, reason="classifier disabled")
        return ClassifierTestResult(category=out.category, confidence=out.confidence, cached=out.cached)

    # ── Main routing entry ───────────────────────────────────────

    async def route(
        self,
        *,
        agent: Agent,
        user_message: str,
        conversation_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        user_role: str = "user",
        user_department_id: uuid.UUID | None = None,
        metadata: dict | None = None,
        trace_lineage: list[uuid.UUID] | None = None,
    ) -> AsyncIterator[OrchestratorEvent]:
        """Main routing + dispatch. Yields OrchestratorEvents; caller
        owns SSE framing + conversation persistence."""
        orch_cfg: dict = dict(agent.orchestrator_config or {})
        default_handler = orch_cfg.get("default_handler")
        if not default_handler:
            yield OrchestratorEvent(
                type="error",
                data={"message": "Orchestrator Agent has no default_handler configured"},
            )
            return

        # ``metadata`` passed from chat router may already be built or may
        # be the raw caller-supplied blob — treat as caller blob, wrap it.
        md = metadata if metadata and "trusted" in metadata else build_metadata(
            user_id=user_id or uuid.UUID(int=0),
            user_role=user_role,
            user_department_id=user_department_id,
            caller_metadata=metadata,
        )

        # Load active rules; evaluate
        rules = await self._active_rules(agent.id)
        msg_input = MatchInput(
            message=user_message,
            metadata=md,
            agent_orchestrator_config=orch_cfg,  # mutated by engine for classifier caching
            db_factory=async_session,
        )

        ctx = DispatchContext(
            agent_id=agent.id,
            conversation_id=conversation_id,
            user_id=user_id,
            trace_id=str(uuid.uuid4()),
            trace_lineage=list(trace_lineage or []),
            db_factory=async_session,
            metadata=md,
        )

        # ── Cascade with fallback_next support ───────────────────
        skip: list[str] = []
        attempt = 0
        MAX_ATTEMPTS = 5  # guard runaway fallback_next chains

        while attempt < MAX_ATTEMPTS:
            attempt += 1
            decision = await engine.evaluate(rules, msg_input, skip_rule_ids=skip)

            # Diagnostic event (caller decides whether to forward to client)
            yield OrchestratorEvent(
                type="orchestrator_decision",
                data={
                    "matched_rule": (
                        {
                            "id": str(decision.matched_rule.id),
                            "match_type": decision.match_type_used,
                            "handler_type": decision.matched_rule.handler_type,
                        }
                        if decision.matched_rule
                        else None
                    ),
                    "tried_rules": decision.tried_rule_ids,
                    "classifier": decision.classifier_output,
                },
            )

            if decision.matched_rule is not None:
                rule = decision.matched_rule
                stream, outcome = await dispatch_matched(rule, user_message, ctx)
                async for ev in stream:
                    yield ev

                # Audit this attempt
                await audit.record_trace(
                    async_session,
                    agent_id=agent.id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    user_message=user_message,
                    metadata_snapshot=md,
                    matched_rule_id=rule.id,
                    match_type_used=decision.match_type_used,
                    match_latency_ms=decision.match_latency_ms,
                    classifier_output=decision.classifier_output,
                    handler_type=rule.handler_type,
                    handler_id=rule.handler_id,
                    handler_latency_ms=outcome.handler_latency_ms,
                    handler_status=outcome.handler_status,
                    tried_rules=decision.tried_rule_ids,
                    error=outcome.error,
                )

                if outcome.handler_status == "ok":
                    return

                # Handler errored → policy
                policy = rule.on_handler_error or "use_default"
                if policy == "return_error":
                    return
                if policy == "fallback_next":
                    skip.append(str(rule.id))
                    # Re-enter loop
                    continue
                # policy == "use_default" → fall through to default
                break

            # No rule matched → default
            break

        # Default handler (or fall-through after use_default)
        stream, outcome = await dispatch_default(default_handler, user_message, ctx)
        async for ev in stream:
            yield ev
        await audit.record_trace(
            async_session,
            agent_id=agent.id,
            conversation_id=conversation_id,
            user_id=user_id,
            user_message=user_message,
            metadata_snapshot=md,
            matched_rule_id=None,
            match_type_used="default",
            match_latency_ms=None,
            classifier_output=None,
            handler_type=default_handler.get("handler_type"),
            handler_id=default_handler.get("handler_id"),
            handler_latency_ms=outcome.handler_latency_ms,
            handler_status=(
                "fallback_default" if skip else outcome.handler_status
            ),
            tried_rules=None,
            error=outcome.error,
        )

    # ── Helpers ──────────────────────────────────────────────────

    async def _active_rules(self, agent_id: uuid.UUID) -> list[AgentRule]:
        stmt = (
            select(AgentRule)
            .where(AgentRule.agent_id == agent_id, AgentRule.is_active.is_(True))
            .order_by(AgentRule.priority.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)

    async def _get_rule(self, agent_id: uuid.UUID, rule_id: uuid.UUID) -> AgentRule:
        rule = await self.db.get(AgentRule, rule_id)
        if rule is None or rule.agent_id != agent_id:
            raise NotFoundError("AgentRule", str(rule_id))
        return rule

    async def _assert_agent_is_orchestrator(self, agent_id: uuid.UUID) -> None:
        agent = await self.db.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError("Agent", str(agent_id))
        if agent.agent_type != "orchestrator":
            raise ValidationError(
                f"Agent {agent_id} is type '{agent.agent_type}', rules only apply to 'orchestrator'"
            )

    async def _validate_rule_against_agent(
        self, agent_id: uuid.UUID, data: AgentRuleCreate,
    ) -> None:
        await self._check_match_against_agent(agent_id, data.match_type, data.match_config)

    async def _check_match_against_agent(
        self, agent_id: uuid.UUID, match_type: str, match_config: dict,
    ) -> None:
        agent = await self.db.get(Agent, agent_id)
        orch_cfg = (agent.orchestrator_config or {}) if agent else {}

        if match_type == "condition":
            whitelist = orch_cfg.get("trusted_metadata_paths") or DEFAULT_TRUSTED_PATHS
            try:
                assert_path_trusted(match_config["path"], whitelist)
            except ValueError as e:
                raise ValidationError(str(e))

        if match_type == "llm_intent":
            classifier = orch_cfg.get("classifier") or {}
            known = {c["name"] for c in (classifier.get("categories") or [])}
            cat = match_config.get("category")
            if cat not in known:
                raise ValidationError(
                    f"llm_intent category '{cat}' not in classifier categories: {sorted(known)}"
                )
