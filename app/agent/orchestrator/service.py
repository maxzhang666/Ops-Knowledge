"""OrchestratorService — rule CRUD + ``route()`` main entry.

``route()`` is the single thing chat/orchestrator_pipeline calls; it
composes engine.evaluate + dispatcher + audit.record_trace. Owns the
``on_handler_error`` state machine: ``fallback_next`` re-enters the
cascade skipping the failed rule; ``use_default`` jumps straight to
the configured default_handler; ``return_error`` surfaces to user.
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import Agent
from app.agent.orchestrator import audit, cache, engine
from app.agent.orchestrator.adapters import DispatchContext
from app.agent.orchestrator.dispatcher import dispatch_default, dispatch_matched
from app.agent.orchestrator.events import OrchestratorEvent
from app.agent.orchestrator.matchers.base import MatchInput
from app.agent.orchestrator.matchers.llm_intent import classify
from app.agent.orchestrator.metadata import assert_path_trusted, build_metadata
from app.agent.orchestrator.models import AgentRule, AgentRuleVersion, OrchestratorTrace
from app.agent.orchestrator.schemas import (
    DEFAULT_DIAG_ROLES,
    DEFAULT_TRUSTED_PATHS,
    AgentRuleCreate,
    AgentRuleMove,
    AgentRuleRollbackRequest,
    AgentRuleUpdate,
    ClassifierAnalytics,
    ClassifierTestResult,
    OrchestratorConfig,
    RuleAnalyticsRow,
)
from app.core.database import async_session
from app.core.exceptions import NotFoundError, ValidationError

logger = structlog.get_logger(__name__)

PRIORITY_STEP = 10.0  # default spacing when appending to end


def _ab_group_for(
    user_id: uuid.UUID | None, agent_id: uuid.UUID,
) -> str | None:
    """Plan 31 N3.3 — stable A/B split.

    Hash(user_id + agent_id) so the SAME user always gets the same group
    on this Agent (can't jump between A/B mid-conversation), but two
    different Agents get independent splits (Agent-scoped experiment).

    Returns None when user_id is absent (e.g. ad-hoc API calls without
    an authenticated session) so admin probing doesn't skew the split.
    """
    if user_id is None:
        return None
    digest = hashlib.sha1(f"{user_id}:{agent_id}".encode("utf-8")).digest()
    return "A" if digest[0] % 2 == 0 else "B"


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
        # Plan 31 N3.2 — seed v1 snapshot so rollback lineage starts from creation
        await self._write_version_snapshot(rule, user_id=created_by, change_note="initial")
        await self.db.flush()
        await self.db.refresh(rule)
        cache.invalidate(agent_id)  # N3.4
        return rule

    async def list_rule_versions(
        self, agent_id: uuid.UUID, rule_id: uuid.UUID,
    ) -> list[AgentRuleVersion]:
        await self._get_rule(agent_id, rule_id)  # ownership check
        rows = (await self.db.execute(
            select(AgentRuleVersion)
            .where(AgentRuleVersion.rule_id == rule_id)
            .order_by(AgentRuleVersion.version.desc())
        )).scalars().all()
        return list(rows)

    async def rollback_rule(
        self,
        agent_id: uuid.UUID,
        rule_id: uuid.UUID,
        data: AgentRuleRollbackRequest,
        user_id: uuid.UUID,
    ) -> AgentRule:
        """Restore rule state to a prior version. Writes a NEW snapshot so
        the rollback itself is auditable (never destroys history)."""
        rule = await self._get_rule(agent_id, rule_id)
        target = (await self.db.execute(
            select(AgentRuleVersion).where(
                AgentRuleVersion.rule_id == rule_id,
                AgentRuleVersion.version == data.version,
            )
        )).scalar_one_or_none()
        if target is None:
            raise NotFoundError("AgentRuleVersion", f"rule={rule_id} version={data.version}")

        # Copy config-layer fields from snapshot (hit stats stay live)
        rule.priority = target.priority
        rule.is_active = target.is_active
        rule.match_type = target.match_type
        rule.match_config = target.match_config
        rule.handler_type = target.handler_type
        rule.handler_id = target.handler_id
        rule.handler_config = target.handler_config
        rule.on_handler_error = target.on_handler_error
        rule.version = (rule.version or 1) + 1
        note = data.change_note or f"rollback to v{data.version}"
        await self._write_version_snapshot(rule, user_id=user_id, change_note=note)
        await self.db.flush()
        await self.db.refresh(rule)
        cache.invalidate(agent_id)  # N3.4
        return rule

    async def _write_version_snapshot(
        self, rule: AgentRule, *, user_id: uuid.UUID | None, change_note: str | None,
    ) -> None:
        snap = AgentRuleVersion(
            rule_id=rule.id,
            version=rule.version,
            priority=rule.priority,
            is_active=rule.is_active,
            match_type=rule.match_type,
            match_config=rule.match_config,
            handler_type=rule.handler_type,
            handler_id=rule.handler_id,
            handler_config=rule.handler_config,
            on_handler_error=rule.on_handler_error,
            change_note=change_note,
            created_by=user_id,
        )
        self.db.add(snap)

    async def update_rule(
        self,
        agent_id: uuid.UUID,
        rule_id: uuid.UUID,
        data: AgentRuleUpdate,
        user_id: uuid.UUID | None = None,
        change_note: str | None = None,
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
        # Plan 31 N3.2 — snapshot the newly-saved state
        await self._write_version_snapshot(rule, user_id=user_id, change_note=change_note)
        await self.db.flush()
        await self.db.refresh(rule)
        cache.invalidate(agent_id)  # N3.4
        return rule

    async def delete_rule(self, agent_id: uuid.UUID, rule_id: uuid.UUID) -> None:
        rule = await self._get_rule(agent_id, rule_id)
        await self.db.delete(rule)
        await self.db.flush()
        cache.invalidate(agent_id)  # N3.4

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
        cache.invalidate(agent_id)  # N3.4
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

        # Load active rules (N3.4 cache-backed)
        rules = await self._active_rules(agent.id, agent=agent)
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

        # Plan 31 N3.3 — stable A/B group per (user, agent). Written into
        # every trace row so analytics can compare group outcomes.
        ab_group = _ab_group_for(user_id, agent.id)

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
                    ab_group=ab_group,
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
            ab_group=ab_group,
            error=outcome.error,
        )

    # ── Analytics (N3.6) ─────────────────────────────────────────

    async def rules_analytics(
        self, agent_id: uuid.UUID, since_days: int,
    ) -> list[RuleAnalyticsRow]:
        """Aggregate orchestrator_traces into per-rule metrics over the last N days.

        Skips the default_handler rows (matched_rule_id IS NULL) — those are
        surfaced separately via the classifier / fallback columns if needed.
        """
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        stmt = (
            select(OrchestratorTrace)
            .where(
                OrchestratorTrace.agent_id == agent_id,
                OrchestratorTrace.created_at >= cutoff,
                OrchestratorTrace.matched_rule_id.isnot(None),
            )
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        buckets: dict[uuid.UUID, dict] = {}
        latency_samples: dict[uuid.UUID, list[int]] = {}
        for r in rows:
            rid = r.matched_rule_id
            assert rid is not None  # guarded by where-clause
            b = buckets.setdefault(rid, {
                "hit_count": 0, "success_count": 0, "error_count": 0,
                "fallback_next_count": 0,
                "ab_split": {"A": 0, "B": 0, "null": 0},
                "total_latency": 0,
                "latency_samples": 0,
            })
            b["hit_count"] += 1
            if r.handler_status == "ok":
                b["success_count"] += 1
            elif r.handler_status == "error":
                b["error_count"] += 1
            elif r.handler_status == "fallback_next":
                b["fallback_next_count"] += 1
            key = r.ab_group if r.ab_group in ("A", "B") else "null"
            b["ab_split"][key] += 1
            if r.handler_latency_ms is not None:
                b["total_latency"] += r.handler_latency_ms
                b["latency_samples"] += 1
                latency_samples.setdefault(rid, []).append(r.handler_latency_ms)

        result: list[RuleAnalyticsRow] = []
        for rid, b in buckets.items():
            samples = sorted(latency_samples.get(rid, []))
            p95 = samples[int(len(samples) * 0.95)] if samples else None
            if p95 is not None and int(len(samples) * 0.95) >= len(samples):
                p95 = samples[-1]
            avg = (b["total_latency"] / b["latency_samples"]) if b["latency_samples"] else None
            result.append(RuleAnalyticsRow(
                rule_id=rid,
                hit_count=b["hit_count"],
                success_count=b["success_count"],
                error_count=b["error_count"],
                fallback_next_count=b["fallback_next_count"],
                avg_latency_ms=avg,
                p95_latency_ms=p95,
                ab_split=b["ab_split"],
            ))
        result.sort(key=lambda x: x.hit_count, reverse=True)
        return result

    async def classifier_analytics(
        self, agent_id: uuid.UUID, since_days: int,
    ) -> ClassifierAnalytics:
        """Classifier hit rate + confidence distribution."""
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        rows = (await self.db.execute(
            select(OrchestratorTrace).where(
                OrchestratorTrace.agent_id == agent_id,
                OrchestratorTrace.created_at >= cutoff,
                OrchestratorTrace.llm_classifier_category.isnot(None),
            )
        )).scalars().all()

        total = len(rows)
        cached = sum(1 for r in rows if r.llm_classifier_cached)
        confidences = [r.llm_classifier_confidence for r in rows if r.llm_classifier_confidence is not None]

        # "low confidence" = below the agent's configured threshold (fallback to 0.6)
        agent = await self.db.get(Agent, agent_id)
        threshold = 0.6
        if agent and agent.orchestrator_config:
            cls_cfg = agent.orchestrator_config.get("classifier") or {}
            threshold = float(cls_cfg.get("confidence_threshold", 0.6))

        categories: dict[str, int] = {}
        low = 0
        for r in rows:
            cat = r.llm_classifier_category or "__unknown__"
            categories[cat] = categories.get(cat, 0) + 1
            if (r.llm_classifier_confidence or 0.0) < threshold:
                low += 1

        return ClassifierAnalytics(
            total_classifications=total,
            cache_hit_rate=(cached / total) if total else 0.0,
            avg_confidence=(sum(confidences) / len(confidences)) if confidences else None,
            category_distribution=categories,
            low_confidence_count=low,
        )

    # ── Helpers ──────────────────────────────────────────────────

    async def _active_rules(
        self, agent_id: uuid.UUID, agent: Agent | None = None,
    ) -> list[AgentRule]:
        # Plan 31 N3.4 — in-memory cache keyed on agent.updated_at.
        # SQLAlchemy onupdate=func.now() bumps updated_at on any agent write,
        # and Agent edits that matter (orchestrator_config changes) always
        # go through Agent update paths. Rule CRUD doesn't bump Agent's
        # updated_at itself, so service.create_rule/update/delete/move
        # explicitly call cache.invalidate below.
        if agent is not None:
            cached = cache.get_cached_rules(agent_id, agent.updated_at)
            if cached is not None:
                return cached
        stmt = (
            select(AgentRule)
            .where(AgentRule.agent_id == agent_id, AgentRule.is_active.is_(True))
            .order_by(AgentRule.priority.asc())
        )
        rows = list((await self.db.execute(stmt)).scalars().all())
        if agent is not None:
            cache.put_cached_rules(agent_id, agent.updated_at, rows)
        return rows

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
        # handler_id must reference a Workflow owned by this Orchestrator (Plan 31 N2.9)
        await self._assert_handler_workflow_owned(agent_id, data.handler_id)

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

    async def _assert_handler_workflow_owned(
        self, agent_id: uuid.UUID, workflow_id: uuid.UUID | None,
    ) -> None:
        """Plan 31 N2.9 — rule's handler_id must reference a Workflow that
        belongs to THIS Orchestrator (workflows.owner_agent_id == agent_id).
        Prevents accidental cross-Agent routing + keeps cascade-delete sane.
        """
        if workflow_id is None:
            return
        from app.workflow.models import Workflow
        wf = await self.db.get(Workflow, workflow_id)
        if wf is None:
            raise ValidationError(f"Workflow {workflow_id} not found")
        if wf.owner_agent_id != agent_id:
            raise ValidationError(
                f"Workflow {workflow_id} is not owned by this Orchestrator — "
                f"create the Workflow inside this Agent's SOP 流程 first"
            )
