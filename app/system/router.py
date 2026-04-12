import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from pymilvus import MilvusClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.core.config import settings
from app.core.database import engine, get_db
from app.system.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyResponse
from app.system.service import ApiKeyService

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    services = {}

    # PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception:
        services["postgres"] = "unavailable"

    # Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        services["redis"] = "ok"
    except Exception:
        services["redis"] = "unavailable"

    # Milvus
    try:
        client = MilvusClient(uri=settings.MILVUS_URI)
        client.list_collections()
        client.close()
        services["milvus"] = "ok"
    except Exception:
        services["milvus"] = "unavailable"

    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"
    return {"status": overall, "version": settings.APP_VERSION, "services": services}


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: ApiKeyCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ApiKeyService(db)
    api_key, raw_key = await svc.create_key(current_user.id, data)
    return ApiKeyCreated(
        id=api_key.id, name=api_key.name, key_prefix=api_key.key_prefix,
        scope=api_key.scope, is_active=api_key.is_active, expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at, created_at=api_key.created_at, raw_key=raw_key,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ApiKeyService(db)
    return await svc.list_keys(current_user.id)


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ApiKeyService(db)
    try:
        await svc.revoke_key(key_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
