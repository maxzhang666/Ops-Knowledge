import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from pymilvus import MilvusClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, require_role
from app.auth.models import User, UserRole
from app.core.config import settings
from app.core.database import engine, get_db
from app.core.runtime_config import get_runtime_config, invalidate_cache, resolve
from app.system.schemas import ApiKeyCreate, ApiKeyResponse
from app.system.service import ApiKeyService

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    services = {}
    cfg = await get_runtime_config(db)
    executor = ThreadPoolExecutor(max_workers=5)
    loop = asyncio.get_event_loop()
    HC_TIMEOUT = 5  # seconds per service

    # PostgreSQL (already async, just add timeout)
    try:
        async with asyncio.timeout(HC_TIMEOUT):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception:
        services["postgres"] = "unavailable"

    # Redis (async with timeout)
    try:
        async with asyncio.timeout(HC_TIMEOUT):
            r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=HC_TIMEOUT, socket_timeout=HC_TIMEOUT)
            await r.ping()
            await r.aclose()
        services["redis"] = "ok"
    except Exception:
        services["redis"] = "unavailable"

    # Milvus (sync client → run in thread with timeout)
    def _hc_milvus():
        milvus_uri = resolve(cfg, "milvus", "uri", settings.MILVUS_URI)
        milvus_token = resolve(cfg, "milvus", "token", None)
        kw: dict = {"uri": milvus_uri, "timeout": HC_TIMEOUT}
        if milvus_token:
            kw["token"] = milvus_token
        c = MilvusClient(**kw)
        c.list_collections()
        c.close()

    try:
        await asyncio.wait_for(loop.run_in_executor(executor, _hc_milvus), timeout=HC_TIMEOUT + 2)
        services["milvus"] = "ok"
    except Exception:
        services["milvus"] = "unavailable"

    # MinIO (sync client → run in thread with timeout)
    def _hc_minio():
        import boto3 as _b3
        from botocore.config import Config as BotoConfig
        from botocore.exceptions import ClientError as BotoErr
        ep = resolve(cfg, "minio", "endpoint", settings.MINIO_ENDPOINT)
        ak = resolve(cfg, "minio", "access_key", settings.MINIO_ACCESS_KEY)
        sk = resolve(cfg, "minio", "secret_key", settings.MINIO_SECRET_KEY)
        sec = resolve(cfg, "minio", "secure", settings.MINIO_SECURE)
        bkt = resolve(cfg, "minio", "bucket", settings.MINIO_BUCKET)
        c = _b3.client("s3", endpoint_url=f"{'https' if sec else 'http'}://{ep}",
                        aws_access_key_id=ak, aws_secret_access_key=sk,
                        config=BotoConfig(signature_version="s3v4", connect_timeout=HC_TIMEOUT,
                                          read_timeout=HC_TIMEOUT, retries={"max_attempts": 0}),
                        region_name="us-east-1")
        try:
            c.head_bucket(Bucket=bkt)
        except BotoErr as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchBucket"):
                c.create_bucket(Bucket=bkt)
            else:
                raise

    try:
        await asyncio.wait_for(loop.run_in_executor(executor, _hc_minio), timeout=HC_TIMEOUT + 2)
        services["minio"] = "ok"
    except Exception:
        services["minio"] = "unavailable"

    # Celery (already has timeout=2)
    def _hc_celery():
        from app.core.celery import celery_app
        return celery_app.control.ping(timeout=2)

    try:
        ping_result = await asyncio.wait_for(loop.run_in_executor(executor, _hc_celery), timeout=HC_TIMEOUT)
        services["celery"] = "ok" if ping_result else "unavailable"
    except Exception:
        services["celery"] = "unavailable"

    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"

    # E12: Auto-notify admin on degradation
    if overall == "degraded":
        try:
            from app.system.models import Notification
            from app.core.database import async_session as async_session_factory
            async with async_session_factory() as notify_db:
                down_services = [k for k, v in services.items() if v != "ok"]
                notif = Notification(
                    user_id=None,
                    type="system",
                    title="服务降级告警",
                    content=f"以下服务不可用: {', '.join(down_services)}",
                    priority="high",
                )
                notify_db.add(notif)
                await notify_db.commit()
        except Exception:
            pass  # notification is best-effort

    return {"status": overall, "version": settings.APP_VERSION, "services": services}


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: ApiKeyCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ApiKeyService(db)
    return await svc.create_key(current_user.id, data)


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ApiKeyService(db)
    return await svc.list_keys(current_user.id)


@router.post("/api-keys/{key_id}/delete", status_code=status.HTTP_200_OK)
async def revoke_api_key(
    key_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = ApiKeyService(db)
    try:
        await svc.revoke_key(key_id, current_user.id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/settings")
async def get_settings(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from app.system.models import SystemSettings
    row = await db.get(SystemSettings, 1)
    return row.settings if row else {}


@router.post("/settings/update")
async def update_settings(
    body: dict,
    _user: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    from app.system.models import SystemSettings
    row = await db.get(SystemSettings, 1)
    if not row:
        row = SystemSettings(id=1, settings=body, updated_by=_user.id)
        db.add(row)
    else:
        row.settings = {**row.settings, **body}
        row.updated_by = _user.id
    await db.flush()
    invalidate_cache()
    # Broadcast to all other processes (web workers + Celery workers)
    from app.core.runtime_config import publish_invalidate
    publish_invalidate()
    return row.settings


@router.post("/test-connection")
async def test_connection(
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    service = body.get("service")
    if service not in ("milvus", "minio", "redis"):
        raise HTTPException(status_code=400, detail="Invalid service. Must be one of: milvus, minio, redis")

    # Merge saved config with ad-hoc overrides from request body
    cfg = await get_runtime_config(db)
    adhoc = body.get("config", {})
    if adhoc:
        cfg = {**cfg, service: {**cfg.get(service, {}), **adhoc}}
    result = {"service": service, "ok": False, "detail": ""}

    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    TIMEOUT = 5  # seconds

    def _test_redis():
        import redis as sync_redis
        r = sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=TIMEOUT, socket_timeout=TIMEOUT)
        r.ping()
        r.close()

    def _test_milvus():
        milvus_uri = resolve(cfg, "milvus", "uri", settings.MILVUS_URI)
        milvus_token = resolve(cfg, "milvus", "token", None)
        kw: dict = {"uri": milvus_uri, "timeout": TIMEOUT}
        if milvus_token:
            kw["token"] = milvus_token
        client = MilvusClient(**kw)
        client.list_collections()
        client.close()

    def _test_minio():
        import boto3 as _boto3
        from botocore.config import Config as BotoConfig
        from botocore.exceptions import ClientError as BotoClientError

        minio_endpoint = resolve(cfg, "minio", "endpoint", settings.MINIO_ENDPOINT)
        minio_access = resolve(cfg, "minio", "access_key", settings.MINIO_ACCESS_KEY)
        minio_secret = resolve(cfg, "minio", "secret_key", settings.MINIO_SECRET_KEY)
        minio_secure = resolve(cfg, "minio", "secure", settings.MINIO_SECURE)
        minio_bucket = resolve(cfg, "minio", "bucket", settings.MINIO_BUCKET)

        client = _boto3.client(
            "s3",
            endpoint_url=f"{'https' if minio_secure else 'http'}://{minio_endpoint}",
            aws_access_key_id=minio_access,
            aws_secret_access_key=minio_secret,
            config=BotoConfig(
                signature_version="s3v4",
                connect_timeout=TIMEOUT,
                read_timeout=TIMEOUT,
                retries={"max_attempts": 0},
            ),
            region_name="us-east-1",
        )
        try:
            client.head_bucket(Bucket=minio_bucket)
        except BotoClientError as me:
            code = me.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchBucket"):
                client.create_bucket(Bucket=minio_bucket)
            else:
                raise

    try:
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=1)

        if service == "redis":
            await asyncio.wait_for(loop.run_in_executor(executor, _test_redis), timeout=TIMEOUT + 2)
        elif service == "milvus":
            await asyncio.wait_for(loop.run_in_executor(executor, _test_milvus), timeout=TIMEOUT + 2)
        elif service == "minio":
            await asyncio.wait_for(loop.run_in_executor(executor, _test_minio), timeout=TIMEOUT + 2)

        result["ok"] = True

    except asyncio.TimeoutError:
        result["detail"] = f"连接超时（{TIMEOUT}s）— 服务可能未启动或地址不可达"
    except Exception as e:
        result["detail"] = str(e)[:500]

    return result
