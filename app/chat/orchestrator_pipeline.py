"""Orchestrator Agent chat pipeline (Plan 31 N1).

Peer to ``pipeline.py`` (RAG) and ``workflow_pipeline.py``. Owns the
outer Conversation + Message rows for the user-facing chat; delegates
routing + handler dispatch to ``OrchestratorService.route`` and
re-emits its ``OrchestratorEvent`` stream as the chat SSE tuples the
frontend already understands.

Debug access is gated here: the caller asks for ``debug=True`` but we
only forward the ``orchestrator_decision`` event if the current user
role appears in the Agent's ``diagnostic_mode_allowed_roles`` whitelist.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.models import Agent
from app.agent.orchestrator.events import OrchestratorEvent
from app.agent.orchestrator.metadata import build_metadata
from app.agent.orchestrator.schemas import DEFAULT_DIAG_ROLES
from app.agent.orchestrator.service import OrchestratorService
from app.chat.service import ConversationService
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Share one engine across pipeline invocations (same pattern as pipeline.py).
_pipeline_engine = None


def _get_pipeline_engine():
    global _pipeline_engine
    if _pipeline_engine is None:
        _pipeline_engine = create_async_engine(
            settings.DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10,
        )
    return _pipeline_engine


async def run_orchestrator_pipeline(
    *,
    agent: Agent,
    query: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID,
    user_role: str = "user",
    user_department_id: uuid.UUID | None = None,
    metadata: dict | None = None,
    debug: bool = False,
) -> AsyncGenerator[tuple[str, dict | str], None]:
    """Run Orchestrator routing and yield SSE tuples compatible with
    the existing frontend contract (message_start / thinking /
    retrieval_info / content_delta / message_end)."""
    engine = _get_pipeline_engine()
    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    db_session = sessionmaker()
    try:
        t0 = time.monotonic()
        conv_svc = ConversationService(db_session)

        if conversation_id:
            conv = await conv_svc.get_conversation(conversation_id)
        else:
            conv = await conv_svc.create_conversation(agent.id, user_id)
            conversation_id = conv.id

        user_msg = await conv_svc.add_message(conversation_id, "user", query)
        trace_id = str(uuid.uuid4())
        assistant_msg = await conv_svc.add_message(
            conversation_id, "assistant", "",
            status="generating", trace_id=trace_id,
        )
        await db_session.commit()

        yield ("message_start", {
            "message_id": str(assistant_msg.id),
            "conversation_id": str(conversation_id),
        })

        # Resolve primary department lazily — Plan 31 condition rules may
        # match on user.department_id. We take the first department in
        # UserDepartment rows (multi-dept support is Phase 3).
        if user_department_id is None:
            try:
                from app.department.service import DepartmentService
                dept_svc = DepartmentService(db_session)
                dept_ids = await dept_svc.get_user_department_ids(user_id)
                user_department_id = dept_ids[0] if dept_ids else None
            except Exception:
                user_department_id = None

        # Compose trusted + input metadata namespaces
        md = build_metadata(
            user_id=user_id,
            user_role=user_role,
            user_department_id=user_department_id,
            caller_metadata=metadata,
        )

        # Debug gating
        allowed_roles = set(
            (agent.orchestrator_config or {}).get(
                "diagnostic_mode_allowed_roles", DEFAULT_DIAG_ROLES,
            ) or DEFAULT_DIAG_ROLES
        )
        debug_allowed = debug and user_role in allowed_roles

        # ── Delegate to the Orchestrator engine ──────────────
        orch = OrchestratorService(db_session)
        full_content = ""
        try:
            async for ev in orch.route(
                agent=agent,
                user_message=query,
                conversation_id=conversation_id,
                user_id=user_id,
                user_role=user_role,
                user_department_id=user_department_id,
                metadata=md,
            ):
                # Forward / filter events
                mapped = _map_event(ev, debug_allowed)
                if mapped is None:
                    continue
                ev_name, payload = mapped
                if ev_name == "content_delta":
                    full_content += payload.get("delta", "") or ""
                yield (ev_name, payload)
        except Exception:
            logger.exception("orchestrator_pipeline_error")
            yield ("content_delta", {"delta": "\n[错误] 路由失败，请检查 Agent 配置。"})

        # Persist final assistant message
        await conv_svc.update_message(
            assistant_msg.id,
            content=full_content or "(empty)",
            status="completed",
            token_usage={"input_tokens": 0, "output_tokens": 0},  # Orchestrator 本身无 token 成本；adapters 各自记账
        )
        await db_session.commit()

        yield ("message_end", {
            "token_usage": {"input_tokens": 0, "output_tokens": 0},
            "trace_id": trace_id,
        })
    finally:
        await db_session.close()


def _map_event(ev: OrchestratorEvent, debug_allowed: bool):
    """Translate OrchestratorEvent → (name, data) tuple for the SSE
    renderer. Gate debug-only events by role."""
    if ev.type == "orchestrator_decision" and not debug_allowed:
        return None  # drop silently
    if ev.type == "adapter_extra" and not debug_allowed:
        return None
    if ev.type == "handler_invoked" and not debug_allowed:
        # Front-end could render a 'routing to X' chip but for non-debug
        # users we hide to keep Orchestrator looking like a Simple Agent.
        return None
    if ev.type == "error":
        # Surface handler errors as visible content so the user isn't
        # left with a blank message.
        return ("content_delta", {"delta": f"\n[错误] {ev.data.get('message') or '路由失败'}"})
    return (ev.type, ev.data)
