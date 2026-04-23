import json
import uuid
from pathlib import Path

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import Agent
from app.agent.schemas import AgentCreate, AgentUpdate
from app.core.dependencies import apply_dept_scope
from app.core.exceptions import NotFoundError
from app.department.models import DepartmentResource
from app.department.service import DepartmentService

logger = structlog.get_logger(__name__)

_SEED_PROMPT_TEMPLATES = Path(__file__).resolve().parent.parent / "core" / "seed" / "prompt_templates.json"


def _default_system_prompt() -> str:
    """Return the ``rag-basic`` template body as the default Agent system prompt.

    Spec 04/16 require new agents to be pre-filled with ``rag-basic`` so they
    are immediately functional (include ``{{context}}`` + citation rules).
    Users can replace this at creation time or from the Persona panel.
    """
    try:
        data = json.loads(_SEED_PROMPT_TEMPLATES.read_text(encoding="utf-8"))
        for tpl in data:
            if tpl.get("id") == "rag-basic":
                return tpl.get("system_prompt", "") or ""
    except Exception:
        logger.warning("rag_basic_template_missing")
    return ""


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_agent(
        self, data: AgentCreate, user_id: uuid.UUID
    ) -> Agent:
        # Default to rag-basic template so new agents work out-of-box
        # (spec 04:32 / 16:121). Caller can override by passing a prompt.
        system_prompt = data.system_prompt if data.system_prompt else _default_system_prompt()

        # Workflow Agent resolution (spec 12 §Phase 1b / 22 §1):
        # "Create Workflow Agent = create Agent + build Workflow in-place" —
        # workflows aren't standalone resources from the user's POV. If the
        # caller didn't supply workflow_id, we provision a fresh draft workflow
        # owned by this agent and bind it. If the caller passed one (e.g.
        # cloning an agent), we validate it exists.
        #
        # Orchestrator Agent (Plan 31 N2.9) — similar pattern but 1:N. We
        # auto-provision ONE default Workflow and wire it as default_handler;
        # user adds more Workflows from the workbench "SOP 流程" menu.
        workflow_id = data.workflow_id
        pending_default_workflow_name: str | None = None
        if data.agent_type == "workflow":
            if workflow_id is None:
                # Owner binding filled in after agent.flush() below
                pending_default_workflow_name = f"{data.name} · 工作流"
            else:
                await self._validate_workflow_binding(workflow_id)
        elif data.agent_type == "orchestrator":
            # Orchestrator: always provision a default Workflow if none wired
            dh = (data.orchestrator_config or {}).get("default_handler") or {}
            if not dh.get("handler_id"):
                pending_default_workflow_name = f"{data.name} · 默认 SOP"

        agent = Agent(
            name=data.name,
            description=data.description,
            avatar=data.avatar,
            agent_type=data.agent_type,
            knowledge_base_ids=data.knowledge_base_ids or [],
            folder_ids=data.folder_ids or [],
            mcp_server_ids=data.mcp_server_ids or [],
            orchestrator_config=data.orchestrator_config,
            model_provider_id=data.model_provider_id,
            model_name=data.model_name,
            system_prompt=system_prompt,
            retrieval_config=data.retrieval_config,
            welcome_message=data.welcome_message,
            show_thinking=data.show_thinking,
            thinking_detail=data.thinking_detail,
            no_result_mode=data.no_result_mode,
            workflow_id=workflow_id,
            created_by=user_id,
        )
        self.db.add(agent)
        await self.db.flush()
        await self.db.refresh(agent)  # load server-generated created_at/updated_at

        # Auto-provision owned Workflow now that we have agent.id.
        # Workflow Agent → writes back to agent.workflow_id (legacy 1:1 field).
        # Orchestrator Agent → wires the Workflow as default_handler.
        if pending_default_workflow_name is not None:
            new_wf_id = await self._provision_draft_workflow_for(
                pending_default_workflow_name, user_id, owner_agent_id=agent.id,
            )
            if data.agent_type == "workflow":
                agent.workflow_id = new_wf_id
            else:  # orchestrator
                cfg = dict(agent.orchestrator_config or {})
                cfg["default_handler"] = {
                    "handler_type": "workflow",
                    "handler_id": str(new_wf_id),
                    "handler_config": {"input_mapping": {"query": "$message"}},
                }
                agent.orchestrator_config = cfg
            await self.db.flush()

        if data.share_to_dept:
            dept_svc = DepartmentService(self.db)
            dept_ids = await dept_svc.get_user_department_ids(user_id)
            for dept_id in dept_ids:
                await dept_svc.share_resource(
                    dept_id, "agent", agent.id, "use", user_id
                )

        await self._attach_share_flag(agent, user_id)
        logger.info("agent_created", agent_id=str(agent.id), name=data.name)
        return agent

    async def get_agent(self, agent_id: uuid.UUID) -> Agent:
        agent = await self.db.get(Agent, agent_id)
        if agent is None or not agent.is_active:
            raise NotFoundError("Agent", str(agent_id))
        return agent

    async def list_agents(
        self,
        user_id: uuid.UUID,
        accessible_ids: list[uuid.UUID] | None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Agent], int]:
        base = select(Agent).where(Agent.is_active.is_(True))
        if accessible_ids is not None:
            stmt = apply_dept_scope(
                base, accessible_ids, user_id, Agent.id, Agent.created_by
            )
        else:
            stmt = base

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        rows = await self.db.scalars(
            stmt.order_by(Agent.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.all()), total

    async def update_agent(
        self,
        agent_id: uuid.UUID,
        data: AgentUpdate,
        user_id: uuid.UUID,
        if_unmodified_since=None,
    ) -> Agent:
        agent = await self.get_agent(agent_id)
        if if_unmodified_since and agent.updated_at != if_unmodified_since:
            from app.core.exceptions import ConflictError
            raise ConflictError("Agent has been modified by another user")
        updates = data.model_dump(exclude_unset=True)
        share_flag = updates.pop("share_to_dept", None)
        # When this is (or becomes) a workflow agent, ensure the workflow_id is
        # valid + published. AgentUpdate doesn't carry agent_type; we gate on
        # the stored value.
        if agent.agent_type == "workflow" and "workflow_id" in updates:
            await self._validate_workflow_binding(updates["workflow_id"])
        for k, v in updates.items():
            setattr(agent, k, v)
        await self.db.flush()
        await self.db.refresh(agent)  # load server-generated updated_at

        if share_flag is not None:
            await self._sync_share_to_dept(agent, user_id, share_flag)

        await self._attach_share_flag(agent, user_id)
        return agent

    async def _validate_workflow_binding(self, workflow_id: uuid.UUID | None) -> None:
        """Validate that the referenced workflow exists.

        NOTE: unlike an early draft of this method, we no longer require the
        workflow be published. Workflow Agents are authored in-place — the
        workflow starts life as a draft inside the Agent config page. Chat
        itself checks `published_graph_data` separately and shows a friendly
        "请先发布" message if absent.
        """
        if workflow_id is None:
            raise ValueError("Workflow Agent requires workflow_id")
        from app.workflow.models import Workflow
        wf = await self.db.get(Workflow, workflow_id)
        if wf is None:
            raise ValueError(f"Workflow {workflow_id} not found")

    async def _provision_draft_workflow_for(
        self,
        workflow_name: str,
        user_id: uuid.UUID | None,
        owner_agent_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Create a draft Workflow owned by an Agent. Used by both Workflow
        Agent (1:1 binding) and Orchestrator Agent (1 of N SOPs)."""
        from app.workflow.service import WorkflowService
        from app.workflow.schemas import WorkflowCreate
        svc = WorkflowService(self.db)
        # Seed with Start node so the editor isn't empty.
        seed_graph = {
            "dsl_version": "1.0",
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "position": {"x": 80, "y": 120}, "data": {}},
                ],
                "edges": [],
            },
            "workflow_variables": [],
        }
        wf = await svc.create(
            WorkflowCreate(
                name=workflow_name,
                description="自动创建",
                graph_data=seed_graph,
            ),
            user_id,
            owner_agent_id=owner_agent_id,
        )
        return wf.id

    async def _sync_share_to_dept(
        self, agent: Agent, user_id: uuid.UUID, share: bool,
    ) -> None:
        dept_svc = DepartmentService(self.db)
        dept_ids = await dept_svc.get_user_department_ids(user_id)
        for dept_id in dept_ids:
            if share:
                try:
                    await dept_svc.share_resource(
                        dept_id, "agent", agent.id, "use", user_id
                    )
                except Exception:
                    pass  # already shared — unique constraint
            else:
                await dept_svc.unshare_resource(dept_id, "agent", agent.id)

    async def _attach_share_flag(self, agent: Agent, user_id: uuid.UUID) -> None:
        """Set non-persisted `share_to_dept` attribute based on current shares."""
        dept_svc = DepartmentService(self.db)
        dept_ids = await dept_svc.get_user_department_ids(user_id)
        if not dept_ids:
            agent.share_to_dept = False
            return
        row = (await self.db.execute(
            select(DepartmentResource.id).where(
                DepartmentResource.resource_type == "agent",
                DepartmentResource.resource_id == agent.id,
                DepartmentResource.department_id.in_(dept_ids),
            ).limit(1)
        )).scalar_one_or_none()
        agent.share_to_dept = row is not None

    async def attach_share_flags(
        self, agents: list[Agent], user_id: uuid.UUID,
    ) -> None:
        """Batch-set share_to_dept on a list of agents (avoids N queries)."""
        if not agents:
            return
        dept_svc = DepartmentService(self.db)
        dept_ids = await dept_svc.get_user_department_ids(user_id)
        if not dept_ids:
            for a in agents:
                a.share_to_dept = False
            return
        shared_ids = set((await self.db.execute(
            select(DepartmentResource.resource_id).where(
                DepartmentResource.resource_type == "agent",
                DepartmentResource.resource_id.in_([a.id for a in agents]),
                DepartmentResource.department_id.in_(dept_ids),
            )
        )).scalars().all())
        for a in agents:
            a.share_to_dept = a.id in shared_ids

    async def delete_agent(self, agent_id: uuid.UUID) -> None:
        agent = await self.get_agent(agent_id)
        agent.is_active = False
        await self.db.flush()
        logger.info("agent_deleted", agent_id=str(agent_id))
