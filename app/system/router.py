import redis.asyncio as aioredis
from fastapi import APIRouter
from pymilvus import MilvusClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

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
