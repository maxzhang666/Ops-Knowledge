import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import Agent
from app.agent.schemas import AgentCreate, AgentUpdate
from app.core.dependencies import apply_dept_scope
from app.core.exceptions import NotFoundError
from app.department.service import DepartmentService

logger = structlog.get_logger(__name__)


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_agent(
        self, data: AgentCreate, user_id: uuid.UUID
    ) -> Agent:
        agent = Agent(
            name=data.name,
            description=data.description,
            avatar=data.avatar,
            knowledge_base_ids=data.knowledge_base_ids,
            folder_ids=data.folder_ids,
            model_provider_id=data.model_provider_id,
            model_name=data.model_name,
            system_prompt=data.system_prompt,
            retrieval_config=data.retrieval_config,
            welcome_message=data.welcome_message,
            show_thinking=data.show_thinking,
            thinking_detail=data.thinking_detail,
            no_result_mode=data.no_result_mode,
            created_by=user_id,
        )
        self.db.add(agent)
        await self.db.flush()

        if data.share_to_dept:
            dept_svc = DepartmentService(self.db)
            dept_ids = await dept_svc.get_user_department_ids(user_id)
            for dept_id in dept_ids:
                await dept_svc.share_resource(
                    dept_id, "agent", agent.id, "use", user_id
                )

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
        accessible_ids: list[uuid.UUID],
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Agent], int]:
        base = select(Agent).where(Agent.is_active.is_(True))
        stmt = apply_dept_scope(
            base, accessible_ids, user_id, Agent.id, Agent.created_by
        )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        rows = await self.db.scalars(
            stmt.order_by(Agent.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.all()), total

    async def update_agent(
        self, agent_id: uuid.UUID, data: AgentUpdate
    ) -> Agent:
        agent = await self.get_agent(agent_id)
        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(agent, k, v)
        await self.db.flush()
        return agent

    async def delete_agent(self, agent_id: uuid.UUID) -> None:
        agent = await self.get_agent(agent_id)
        agent.is_active = False
        await self.db.flush()
        logger.info("agent_deleted", agent_id=str(agent_id))
