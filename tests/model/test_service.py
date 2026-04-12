import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.schemas import ModelsAvailable, ProviderCreate, ProviderUpdate
from app.model.service import ModelService

pytestmark = pytest.mark.asyncio

USER_ID = uuid.uuid4()


def _make_create_data(**overrides) -> ProviderCreate:
    defaults = dict(
        name="TestProvider",
        type="openai_compat",
        base_url="http://localhost:8000/v1",
        api_key="sk-test",
        models_available=ModelsAvailable(llm=["gpt-4o"], embedding=["text-embedding-3-small"]),
        default_llm_model="gpt-4o",
        default_embedding_model="text-embedding-3-small",
    )
    defaults.update(overrides)
    return ProviderCreate(**defaults)


async def test_create_provider(db_session: AsyncSession):
    svc = ModelService(db_session)
    provider = await svc.create_provider(_make_create_data(), USER_ID)
    assert provider.name == "TestProvider"
    assert provider.type == "openai_compat"
    assert provider.created_by == USER_ID


async def test_list_providers(db_session: AsyncSession):
    svc = ModelService(db_session)
    await svc.create_provider(_make_create_data(name="P1"), USER_ID)
    await svc.create_provider(_make_create_data(name="P2"), USER_ID)
    providers = await svc.list_providers()
    assert len(providers) >= 2


async def test_get_provider(db_session: AsyncSession):
    svc = ModelService(db_session)
    created = await svc.create_provider(_make_create_data(), USER_ID)
    fetched = await svc.get_provider(created.id)
    assert fetched is not None
    assert fetched.id == created.id


async def test_update_provider(db_session: AsyncSession):
    svc = ModelService(db_session)
    created = await svc.create_provider(_make_create_data(), USER_ID)
    updated = await svc.update_provider(created.id, ProviderUpdate(name="Renamed"))
    assert updated.name == "Renamed"


async def test_delete_provider(db_session: AsyncSession):
    svc = ModelService(db_session)
    created = await svc.create_provider(_make_create_data(), USER_ID)
    await svc.delete_provider(created.id)
    assert await svc.get_provider(created.id) is None
