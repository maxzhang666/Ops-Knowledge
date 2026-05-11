"""Unit tests for ModelService.chat_by_agent dispatcher (no DB)."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.model.service import AgentModelNotConfigured, ModelService

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def setup_db():
    """Override the root autouse PG fixture — these tests don't touch DB."""
    yield


def _agent(*, model_id=None, provider_id=None, model_name=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        model_id=model_id,
        model_provider_id=provider_id,
        model_name=model_name,
    )


async def test_chat_by_agent_prefers_registry():
    svc = ModelService(db=None)  # no DB needed; sub-calls are mocked
    svc.chat_by_registry = AsyncMock(return_value={"choices": [{"message": {"content": "ok"}}]})
    svc.chat = AsyncMock()

    registry_id = uuid.uuid4()
    agent = _agent(
        model_id=registry_id,
        provider_id=uuid.uuid4(),  # legacy fields also set — registry must win
        model_name="legacy-model",
    )
    result = await svc.chat_by_agent(agent, [{"role": "user", "content": "hi"}], max_tokens=10)

    assert result["choices"][0]["message"]["content"] == "ok"
    svc.chat_by_registry.assert_awaited_once_with(
        registry_id, [{"role": "user", "content": "hi"}], max_tokens=10,
    )
    svc.chat.assert_not_awaited()


async def test_chat_by_agent_falls_back_to_legacy():
    svc = ModelService(db=None)
    svc.chat_by_registry = AsyncMock()
    svc.chat = AsyncMock(return_value={"choices": [{"message": {"content": "legacy"}}]})

    provider_id = uuid.uuid4()
    agent = _agent(model_id=None, provider_id=provider_id, model_name="gpt-4o")
    result = await svc.chat_by_agent(agent, [{"role": "user", "content": "hi"}], max_tokens=50)

    assert result["choices"][0]["message"]["content"] == "legacy"
    svc.chat.assert_awaited_once_with(
        provider_id, "gpt-4o", [{"role": "user", "content": "hi"}], max_tokens=50,
    )
    svc.chat_by_registry.assert_not_awaited()


async def test_chat_by_agent_raises_when_unconfigured():
    svc = ModelService(db=None)
    svc.chat_by_registry = AsyncMock()
    svc.chat = AsyncMock()

    agent = _agent(model_id=None, provider_id=None, model_name=None)
    with pytest.raises(AgentModelNotConfigured):
        await svc.chat_by_agent(agent, [{"role": "user", "content": "hi"}])

    svc.chat_by_registry.assert_not_awaited()
    svc.chat.assert_not_awaited()


async def test_chat_by_agent_partial_legacy_raises():
    """Only one of provider_id / model_name set → still treated as unconfigured."""
    svc = ModelService(db=None)
    svc.chat_by_registry = AsyncMock()
    svc.chat = AsyncMock()

    agent_a = _agent(provider_id=uuid.uuid4(), model_name=None)
    agent_b = _agent(provider_id=None, model_name="gpt-4o")
    for ag in (agent_a, agent_b):
        with pytest.raises(AgentModelNotConfigured):
            await svc.chat_by_agent(ag, [{"role": "user", "content": "hi"}])
