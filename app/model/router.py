import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.core.database import get_db
from app.model.schemas import (
    ProviderCreate,
    ProviderResponse,
    ProviderUpdate,
    RegistryEntryCreate,
    RegistryEntryResponse,
    RegistryEntryUpdate,
    TestResult,
)
from app.model.providers import list_provider_schemas
from app.model.service import ModelService

router = APIRouter(prefix="/model", tags=["model"])


class DiscoverRequest(BaseModel):
    type: str
    base_url: str | None = None
    api_key: str | None = None


@router.get("/provider-types")
async def list_provider_types(current_user: CurrentUser):
    """Provider registry schema: one entry per supported ``type`` with label,
    fields, and capabilities. Frontend uses this for dynamic form rendering.
    """
    return list_provider_schemas()


@router.post("/discover")
async def discover_models(
    data: DiscoverRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    try:
        models = await svc.discover_models(data.type, data.base_url, data.api_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"models": models}


# ── Registry endpoints (before /{provider_id} to avoid path conflict) ──


@router.get("/registry")
async def list_registry(
    current_user: CurrentUser,
    model_type: str | None = None,
    provider_id: uuid.UUID | None = None,
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    return await svc.list_registry(model_type, provider_id, enabled_only)


@router.post("/registry", status_code=status.HTTP_201_CREATED)
async def create_registry_entry(
    data: RegistryEntryCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    entry = await svc.create_registry_entry(data)
    return RegistryEntryResponse.model_validate(entry)


@router.post("/registry/{entry_id}/update")
async def update_registry_entry(
    entry_id: uuid.UUID,
    data: RegistryEntryUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    try:
        entry = await svc.update_registry_entry(entry_id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return RegistryEntryResponse.model_validate(entry)


@router.post("/registry/{entry_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registry_entry(
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    try:
        await svc.delete_registry_entry(entry_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/registry/sync/{provider_id}")
async def sync_registry(
    provider_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    try:
        new_entries = await svc.sync_registry(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"synced": len(new_entries)}


# ── Provider endpoints ──────────────────────────────────────────


@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    data: ProviderCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    provider = await svc.create_provider(data, current_user.id)
    return provider


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    current_user: CurrentUser,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    return await svc.list_providers(active_only=active_only)


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    provider = await svc.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


@router.post("/{provider_id}/update", response_model=ProviderResponse)
async def update_provider(
    provider_id: uuid.UUID,
    data: ProviderUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    try:
        return await svc.update_provider(provider_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{provider_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    try:
        await svc.delete_provider(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{provider_id}/test", response_model=TestResult)
async def test_connectivity(
    provider_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    try:
        return await svc.test_connectivity(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
