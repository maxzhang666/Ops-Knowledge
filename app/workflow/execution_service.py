"""Bridges the LangGraph execution engine ↔ database. Creates
WorkflowExecution rows, runs the compiled graph, and persists final state
+ per-node execution rows."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.integration.event_bus import publish as publish_event
from app.integration.events import Event
from app.workflow.dsl import parse_dsl
from app.workflow.events import EventBus
from app.workflow.models import NodeExecution, Workflow, WorkflowExecution

log = logging.getLogger(__name__)


class WorkflowNotPublished(Exception):
    pass


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_execution(
        self,
        wf_id: uuid.UUID,
        user_id: uuid.UUID | None,
        trigger_input: dict | None,
        *,
        from_draft: bool = False,
    ) -> WorkflowExecution:
        """Create a pending execution row.

        `from_draft=True` (Debug Panel) skips the published-version
        requirement so authors can iterate in the editor without re-publishing
        on every tweak. `workflow_version=0` marks the row as a draft run.
        Production paths (webhook / Agent chat) keep the default so a
        half-edited draft can't leak to end users."""
        wf = await self.db.get(Workflow, wf_id)
        if wf is None:
            raise WorkflowNotPublished(str(wf_id))
        if not from_draft and wf.published_graph_data is None:
            raise WorkflowNotPublished(str(wf_id))
        row = WorkflowExecution(
            workflow_id=wf_id,
            workflow_version=0 if from_draft else wf.version,
            status="pending",
            trigger_input=trigger_input or {},
            created_by=user_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def run_and_persist(
        self,
        execution: WorkflowExecution,
        bus: EventBus,
    ) -> WorkflowExecution:
        wf = await self.db.get(Workflow, execution.workflow_id)
        # workflow_version == 0 means the caller requested a draft-mode run.
        # Strict parse_dsl still runs (validate structure) so malformed drafts
        # fail fast; the published cut isn't touched.
        graph_source = (
            wf.graph_data if execution.workflow_version == 0 else wf.published_graph_data
        )
        dsl = parse_dsl(graph_source)

        execution.status = "running"
        execution.started_at = datetime.now(timezone.utc)
        await self.db.flush()

        resolved_vars = {v.name: v.default for v in dsl.workflow_variables}

        final_status, outputs, inputs, error = await self._run_with_langgraph(
            dsl=dsl, execution=execution, bus=bus,
            workflow_variables=resolved_vars,
        )

        execution.status = final_status
        execution.output = outputs
        execution.error = error
        execution.finished_at = datetime.now(timezone.utc)

        node_type_by_id = {n.id: n.type for n in dsl.graph.nodes}
        # Persist one NodeExecution row per node that actually produced output
        # (skipped branches are NOT persisted — they are N-select-1 noise and
        # would pollute the Process drawer). Same rule for both engines.
        for nid, output in outputs.items():
            self.db.add(NodeExecution(
                execution_id=execution.id,
                node_id=nid,
                node_type=node_type_by_id.get(nid, "unknown"),
                status="succeeded" if final_status != "failed" or nid in outputs else "failed",
                input_data=inputs.get(nid),
                output_data=output,
                started_at=execution.started_at,
                finished_at=execution.finished_at,
            ))
        await self.db.flush()

        duration_ms = None
        if execution.started_at and execution.finished_at:
            duration_ms = int(
                (execution.finished_at - execution.started_at).total_seconds() * 1000
            )
        await publish_event(Event(
            name=(
                "workflow.execution_completed" if final_status == "succeeded"
                else "workflow.execution_failed"
            ),
            source="workflow",
            data={
                "execution_id": str(execution.id),
                "workflow_id": str(execution.workflow_id),
                "status": final_status,
                "duration_ms": duration_ms,
            },
        ))
        return execution

    async def resume_execution(
        self,
        execution: WorkflowExecution,
        bus: EventBus,
        resume_value,
    ) -> WorkflowExecution:
        """Re-enter a waiting execution with a ``Command(resume=value)``.

        Precondition: ``execution.status == "waiting"``."""
        if execution.status != "waiting":
            raise ValueError(
                f"execution {execution.id} is not waiting "
                f"(current status: {execution.status})"
            )

        wf = await self.db.get(Workflow, execution.workflow_id)
        graph_source = (
            wf.graph_data if execution.workflow_version == 0 else wf.published_graph_data
        )
        dsl = parse_dsl(graph_source)
        resolved_vars = {v.name: v.default for v in dsl.workflow_variables}

        execution.status = "running"
        await self.db.flush()

        final_status, outputs, inputs, error = await self._run_with_langgraph(
            dsl=dsl, execution=execution, bus=bus,
            workflow_variables=resolved_vars,
            resume_value=resume_value,
        )

        execution.status = final_status
        execution.output = outputs
        execution.error = error
        execution.finished_at = datetime.now(timezone.utc)

        # Refresh NodeExecution rows — delete old ones and rewrite with the
        # resume-era final state. Simplest approach; alternative is to
        # upsert per node_id. For multi-interrupt flows (rare) we'd need
        # upsert; Phase 4c keeps it simple.
        from sqlalchemy import delete
        await self.db.execute(
            delete(NodeExecution).where(NodeExecution.execution_id == execution.id)
        )
        node_type_by_id = {n.id: n.type for n in dsl.graph.nodes}
        for nid, output in outputs.items():
            self.db.add(NodeExecution(
                execution_id=execution.id,
                node_id=nid,
                node_type=node_type_by_id.get(nid, "unknown"),
                status="succeeded",
                input_data=inputs.get(nid),
                output_data=output,
                started_at=execution.started_at,
                finished_at=execution.finished_at,
            ))
        await self.db.flush()

        await publish_event(Event(
            name=(
                "workflow.execution_completed" if final_status == "succeeded"
                else "workflow.execution_failed" if final_status == "failed"
                else "workflow.execution_waiting"
            ),
            source="workflow",
            data={
                "execution_id": str(execution.id),
                "workflow_id": str(execution.workflow_id),
                "status": final_status,
            },
        ))
        return execution

    async def _run_with_langgraph(
        self, *, dsl, execution, bus, workflow_variables, resume_value=None,
    ) -> tuple[str, dict, dict, str | None]:
        """LangGraph-backed path (Plan 29). Compiles the DSL, streams events
        onto ``bus``, harvests final per-node inputs/outputs from state.

        **Thread scope (Phase 4b):**
        - If ``trigger_input.conversation_id`` is present (Workflow Agent
          chat path) → ``thread_id = conversation_id``. Successive turns in
          the same conversation share LangGraph's checkpointed state, which
          is the basis for multi-turn semantics, crash-resume, and HITL.
        - Otherwise (webhook / manual / one-shot run) → ``thread_id =
          execution_id`` so each run has its own isolated thread.
        """
        # Local imports so the default (legacy) path doesn't pay the LangGraph
        # import cost / require the dependency to be installed.
        from app.workflow.langgraph.checkpoint import get_checkpointer
        from app.workflow.langgraph.compiler import compile_dsl
        from app.workflow.langgraph.events import stream_execution
        from app.workflow.langgraph.state import initial_state

        checkpointer = get_checkpointer()
        compiled = compile_dsl(dsl, checkpointer=checkpointer)

        if resume_value is not None:
            # HITL resume: pass ``Command(resume=value)`` as the invocation
            # input. LangGraph loads the paused state from the checkpointer
            # (via thread_id) and re-runs the interrupted node with the
            # value available on the interrupt() call.
            from langgraph.types import Command
            initial = Command(resume=resume_value)
        else:
            initial = initial_state(
                trigger_input=execution.trigger_input,
                workflow_variables=workflow_variables,
            )

        trigger = execution.trigger_input or {}
        conversation_id = trigger.get("conversation_id")
        thread_id = str(conversation_id) if conversation_id else str(execution.id)
        log.info(
            "langgraph_thread_scope execution_id=%s thread_id=%s scope=%s",
            execution.id, thread_id,
            "conversation" if conversation_id else "execution",
        )

        try:
            final_state = await stream_execution(
                compiled, initial, bus,
                execution_id=str(execution.id),
                thread_id=thread_id,
            )
            outputs = final_state.get("outputs", {}) or {}
            inputs = final_state.get("inputs", {}) or {}
            # HITL: graph paused on an interrupt. Execution isn't done yet —
            # the resume API will re-enter with Command(resume=...) and finish.
            if final_state.get("_status") == "waiting":
                return "waiting", outputs, inputs, None
            return "succeeded", outputs, inputs, None
        except Exception as e:  # noqa: BLE001
            log.exception("LangGraph execution %s failed", execution.id)
            return "failed", {}, {}, str(e)
