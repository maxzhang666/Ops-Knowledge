"""Workflow Agent chat pipeline — same (event, payload) contract as
`app.chat.pipeline.run_rag_pipeline` but driven by a compiled LangGraph.

Maps bus events → SSE event tuples:
  stream_chunk (LLM)                  → content_delta
  node_start (knowledge-retrieval)    → thinking step 0
  node_start (llm)                    → thinking step 1
  node_output (knowledge-retrieval)   → retrieval_info
  node_output (llm)                   → aggregate token_usage
  workflow_end                        → message_end (with token_usage + trace_id)

Multi-turn is handled by LangGraph's checkpointer (``thread_id =
conversation_id``); we no longer construct ``trigger_input.history``.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator

import structlog

from app.chat.service import ConversationService
from app.core.database import async_session
from app.core.observability import get_client
from app.integration.event_bus import publish as publish_event
from app.integration.events import Event as BusEvent
from app.observability.workflow_instrument import (
    attach_bus_instrumentation,
    current_trace,
)
from app.workflow.dsl import parse_dsl
from app.workflow.events import Event as SchedEvent, EventBus
from app.workflow.langgraph.checkpoint import get_checkpointer
from app.workflow.langgraph.compiler import compile_dsl
from app.workflow.langgraph.events import stream_execution
from app.workflow.langgraph.state import initial_state
from app.workflow.models import Workflow

logger = structlog.get_logger(__name__)


async def run_workflow_pipeline(
    *,
    agent,
    query: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> AsyncGenerator[tuple[str, dict], None]:
    if not agent.workflow_id:
        yield ("content_delta", {"delta": "Workflow Agent 未绑定工作流。"})
        yield ("message_end", {
            "token_usage": {"input_tokens": 0, "output_tokens": 0}, "trace_id": None,
        })
        return

    # Prepare conversation + persist user message up front (the graph driver
    # opens its own session below).
    async with async_session() as db:
        conv_svc = ConversationService(db)
        if conversation_id is None:
            conv = await conv_svc.create_conversation(
                agent_id=agent.id, user_id=user_id, title=query[:80],
            )
        else:
            conv = await conv_svc.get_conversation(conversation_id)
        conversation_id = conv.id

        user_msg = await conv_svc.add_message(
            conversation_id=conversation_id, role="user", content=query,
        )

        wf = await db.get(Workflow, agent.workflow_id)
        if wf is None or wf.published_graph_data is None:
            yield ("message_start", {
                "message_id": str(user_msg.id),
                "conversation_id": str(conversation_id),
            })
            yield ("content_delta", {"delta": "工作流未发布，请先发布后再对话。"})
            yield ("message_end", {
                "token_usage": {"input_tokens": 0, "output_tokens": 0}, "trace_id": None,
            })
            return

        dsl = parse_dsl(wf.published_graph_data)
        await db.commit()

    yield ("message_start", {
        "message_id": str(user_msg.id),
        "conversation_id": str(conversation_id),
    })

    execution_id = uuid.uuid4()
    bus = EventBus()

    # Langfuse trace — no-op if unconfigured. The context var lets LLM / other
    # nodes attach Generation spans without an explicit handle.
    _trace = get_client().trace(
        name="workflow.execute",
        user_id=str(user_id),
        metadata={
            "agent_id": str(agent.id),
            "workflow_id": str(agent.workflow_id),
            "execution_id": str(execution_id),
            "conversation_id": str(conversation_id),
        },
    )
    _trace_token = current_trace.set(_trace)
    instr_task = attach_bus_instrumentation(bus, _trace)

    # Compile + initialise. thread_id = conversation_id so successive turns
    # accumulate state via the checkpointer (Plan 29 Phase 4b).
    compiled = compile_dsl(dsl, checkpointer=get_checkpointer())
    initial = initial_state(
        trigger_input={
            "content": query,
            "conversation_id": str(conversation_id),
            "metadata": {"user_id": str(user_id)},
        },
        workflow_variables={v.name: v.default for v in dsl.workflow_variables},
    )

    final_state_holder: dict = {}
    final_status_holder: dict = {"status": "succeeded"}

    async def _driver() -> None:
        try:
            final_state_holder["result"] = await stream_execution(
                compiled, initial, bus,
                execution_id=str(execution_id),
                thread_id=str(conversation_id),
            )
        except Exception as e:  # noqa: BLE001
            final_status_holder["status"] = "failed"
            logger.warning(
                "workflow_pipeline_driver_failed",
                execution_id=str(execution_id), error=str(e),
            )
        finally:
            await bus.close()

    driver_task = asyncio.create_task(_driver())
    q = bus.subscribe()

    # Map node_id → type so we can classify events without duplicating the
    # information in every bus message.
    node_type_by_id = {n.id: n.type for n in dsl.graph.nodes}

    final_parts: list[str] = []
    retrieval_payload: dict | None = None
    token_usage: dict = {"input_tokens": 0, "output_tokens": 0}

    try:
        async for ev in bus.stream(q):
            mapped = _map_event(ev, final_parts, token_usage, node_type_by_id)
            if mapped is None:
                continue
            kind, payload = mapped
            if kind == "retrieval_info":
                retrieval_payload = payload
            yield (kind, payload)
    except asyncio.CancelledError:
        driver_task.cancel()
        raise
    finally:
        try:
            await driver_task
        except asyncio.CancelledError:
            pass
        try:
            await asyncio.wait_for(instr_task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            instr_task.cancel()
        current_trace.reset(_trace_token)
        try:
            _trace.update(output={"status": final_status_holder["status"]})
        except Exception:  # noqa: BLE001
            pass

    # When Answer runs with stream=false (or the DSL has no streaming LLM),
    # `final_parts` stays empty. Recover text from the Answer node's output.
    if not final_parts:
        outputs = (final_state_holder.get("result") or {}).get("outputs") or {}
        for _nid, outs in outputs.items():
            if isinstance(outs, dict) and outs.get("answer"):
                final_parts.append(str(outs["answer"]))
                break

    final_text = "".join(final_parts) or "（工作流无输出）"
    async with async_session() as db:
        conv_svc = ConversationService(db)
        await conv_svc.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=final_text,
            metadata={"retrieval_info": retrieval_payload} if retrieval_payload else None,
            token_usage=token_usage,
            trace_id=str(execution_id),
        )
        await db.commit()

    await publish_event(BusEvent(
        name=(
            "workflow.execution_completed" if final_status_holder["status"] == "succeeded"
            else "workflow.execution_failed"
        ),
        source="workflow",
        data={
            "execution_id": str(execution_id),
            "workflow_id": str(agent.workflow_id),
            "agent_id": str(agent.id),
            "conversation_id": str(conversation_id),
            "status": final_status_holder["status"],
        },
    ))

    yield ("message_end", {
        "token_usage": token_usage,
        "trace_id": str(execution_id),
    })


def _map_event(
    ev: SchedEvent,
    acc: list[str],
    token_usage: dict,
    node_type_by_id: dict[str, str],
) -> tuple[str, dict] | None:
    if ev.type == "stream_chunk":
        delta = ev.data.get("delta") or ""
        if delta:
            acc.append(delta)
            return ("content_delta", {"delta": delta})
        return None

    if ev.type == "node_start":
        ntype = node_type_by_id.get(ev.node_id or "", "")
        if ntype == "knowledge-retrieval":
            return ("thinking", {"step": 0, "content": "检索知识库..."})
        if ntype == "llm":
            return ("thinking", {"step": 1, "content": "生成中..."})
        return None

    if ev.type == "node_output":
        outputs = ev.data.get("outputs") or {}
        if isinstance(outputs.get("chunks"), list):
            return ("retrieval_info", {"chunks": [
                {
                    "id": c.get("id"),
                    "content_preview": (c.get("content") or "")[:300],
                    "score": c.get("score"),
                    "document_title": c.get("document_title"),
                }
                for c in outputs["chunks"]
            ]})
        usage = outputs.get("token_usage")
        if isinstance(usage, dict):
            token_usage["input_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
            token_usage["output_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        return None

    # workflow_start / workflow_end / node_end / node_error → no SSE equivalent.
    return None
