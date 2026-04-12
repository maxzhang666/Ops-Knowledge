"""Conversation service tests (DB-dependent, require running PostgreSQL)."""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.service import ConversationService
from app.core.exceptions import NotFoundError


@pytest.fixture
def svc(db_session: AsyncSession) -> ConversationService:
    return ConversationService(db_session)


@pytest.fixture
def agent_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.mark.asyncio
async def test_create_conversation(
    svc: ConversationService, agent_id: uuid.UUID, user_id: uuid.UUID
):
    conv = await svc.create_conversation(agent_id, user_id, title="Test")
    assert conv.id is not None
    assert conv.agent_id == agent_id
    assert conv.user_id == user_id
    assert conv.message_count == 0


@pytest.mark.asyncio
async def test_get_conversation(
    svc: ConversationService, agent_id: uuid.UUID, user_id: uuid.UUID
):
    conv = await svc.create_conversation(agent_id, user_id)
    found = await svc.get_conversation(conv.id)
    assert found.id == conv.id


@pytest.mark.asyncio
async def test_get_conversation_not_found(svc: ConversationService):
    with pytest.raises(NotFoundError):
        await svc.get_conversation(uuid.uuid4())


@pytest.mark.asyncio
async def test_list_conversations(
    svc: ConversationService, agent_id: uuid.UUID, user_id: uuid.UUID
):
    await svc.create_conversation(agent_id, user_id, title="Conv 1")
    await svc.create_conversation(agent_id, user_id, title="Conv 2")
    items, total = await svc.list_conversations(agent_id, user_id)
    assert total == 2
    assert len(items) == 2


@pytest.mark.asyncio
async def test_add_message(
    svc: ConversationService, agent_id: uuid.UUID, user_id: uuid.UUID
):
    conv = await svc.create_conversation(agent_id, user_id)
    msg = await svc.add_message(conv.id, "user", "Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


@pytest.mark.asyncio
async def test_get_messages(
    svc: ConversationService, agent_id: uuid.UUID, user_id: uuid.UUID
):
    conv = await svc.create_conversation(agent_id, user_id)
    await svc.add_message(conv.id, "user", "Hi")
    await svc.add_message(conv.id, "assistant", "Hello")
    messages = await svc.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"


@pytest.mark.asyncio
async def test_delete_conversation(
    svc: ConversationService, agent_id: uuid.UUID, user_id: uuid.UUID
):
    conv = await svc.create_conversation(agent_id, user_id)
    await svc.delete_conversation(conv.id)
    with pytest.raises(NotFoundError):
        await svc.get_conversation(conv.id)
