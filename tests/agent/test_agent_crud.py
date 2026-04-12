"""Agent CRUD tests (DB-dependent, require running PostgreSQL)."""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import AgentCreate, AgentUpdate
from app.agent.service import AgentService
from app.core.exceptions import NotFoundError


@pytest.fixture
def svc(db_session: AsyncSession) -> AgentService:
    return AgentService(db_session)


@pytest.fixture
def provider_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def agent_data(provider_id: uuid.UUID) -> AgentCreate:
    return AgentCreate(
        name="Test Agent",
        description="A test agent",
        model_provider_id=provider_id,
        model_name="gpt-4",
        knowledge_base_ids=["kb1", "kb2"],
        share_to_dept=False,
    )


@pytest.mark.asyncio
async def test_create_agent(svc: AgentService, agent_data: AgentCreate):
    user_id = uuid.uuid4()
    agent = await svc.create_agent(agent_data, user_id)
    assert agent.id is not None
    assert agent.name == "Test Agent"
    assert agent.created_by == user_id
    assert agent.is_active is True


@pytest.mark.asyncio
async def test_get_agent(svc: AgentService, agent_data: AgentCreate):
    user_id = uuid.uuid4()
    agent = await svc.create_agent(agent_data, user_id)
    found = await svc.get_agent(agent.id)
    assert found.name == "Test Agent"


@pytest.mark.asyncio
async def test_get_agent_not_found(svc: AgentService):
    with pytest.raises(NotFoundError):
        await svc.get_agent(uuid.uuid4())


@pytest.mark.asyncio
async def test_update_agent(svc: AgentService, agent_data: AgentCreate):
    user_id = uuid.uuid4()
    agent = await svc.create_agent(agent_data, user_id)
    updated = await svc.update_agent(
        agent.id, AgentUpdate(name="Updated Agent")
    )
    assert updated.name == "Updated Agent"


@pytest.mark.asyncio
async def test_delete_agent(svc: AgentService, agent_data: AgentCreate):
    user_id = uuid.uuid4()
    agent = await svc.create_agent(agent_data, user_id)
    await svc.delete_agent(agent.id)
    with pytest.raises(NotFoundError):
        await svc.get_agent(agent.id)
