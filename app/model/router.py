import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.core.database import get_db
from app.model.schemas import ProviderCreate, ProviderResponse, ProviderUpdate, TestResult
from app.model.service import ModelService

router = APIRouter(prefix="/model", tags=["model"])


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
    active_only: bool = False,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    return await svc.list_providers(active_only=active_only)


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    provider = await svc.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: uuid.UUID,
    data: ProviderUpdate,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    try:
        return await svc.update_provider(provider_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: uuid.UUID,
    current_user: CurrentUser = None,
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
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    svc = ModelService(db)
    try:
        return await svc.test_connectivity(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
