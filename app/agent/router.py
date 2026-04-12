import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import AgentCreate, AgentResponse, AgentUpdate
from app.agent.service import AgentService
from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.department.service import DepartmentService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentService(db)
    agent = await svc.create_agent(data, current_user.id)
    return agent


@router.get("", response_model=PaginatedResponse)
async def list_agents(
    current_user: CurrentUser,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    dept_svc = DepartmentService(db)
    accessible_ids = await dept_svc.get_accessible_resource_ids(
        current_user.id, "agent"
    )
    svc = AgentService(db)
    items, total = await svc.list_agents(
        current_user.id, accessible_ids, pagination.offset, pagination.page_size
    )
    return PaginatedResponse(
        items=[AgentResponse.model_validate(i) for i in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentService(db)
    agent = await svc.get_agent(agent_id)
    await check_resource_access(
        current_user, "agent", agent.id, db, agent.created_by
    )
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    data: AgentUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentService(db)
    agent = await svc.get_agent(agent_id)
    await check_resource_access(
        current_user, "agent", agent.id, db, agent.created_by, "edit"
    )
    return await svc.update_agent(agent_id, data)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentService(db)
    agent = await svc.get_agent(agent_id)
    await check_resource_access(
        current_user, "agent", agent.id, db, agent.created_by, "full"
    )
    await svc.delete_agent(agent_id)
