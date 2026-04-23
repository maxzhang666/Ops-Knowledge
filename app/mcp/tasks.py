"""Celery tasks for MCP (Plan 30 M3.2).

``mcp_health_check`` runs on Celery beat — every 5 min it iterates every
active MCP server, attempts handshake, and updates ``health_status`` +
``last_checked_at``. Transitions from healthy → unreachable emit an
admin notification.

Each handshake is capped at ``HEALTH_CHECK_TIMEOUT`` seconds so a single
wedged server can't stall the whole sweep.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.mcp.models import MCPServer
from app.mcp.transports import get_transport

logger = structlog.get_logger(__name__)

HEALTH_CHECK_TIMEOUT = 10  # seconds per server


@shared_task(name="app.mcp.tasks.mcp_health_check")
def mcp_health_check() -> dict:
    """Celery entry — delegates to the async impl in a fresh event loop."""
    return asyncio.run(_run_health_check())


async def _run_health_check() -> dict:
    """Iterate active MCP servers, probe each, write back health state."""
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ok = 0
    unreachable = 0
    newly_failed: list[MCPServer] = []
    try:
        async with sessionmaker() as db:
            rows = (await db.execute(
                select(MCPServer).where(MCPServer.is_active.is_(True))
            )).scalars().all()

            for server in rows:
                previous = server.health_status
                status = await _probe(server)
                server.health_status = status
                server.last_checked_at = datetime.now(timezone.utc)
                if status == "ok":
                    ok += 1
                else:
                    unreachable += 1
                    # Transition OK/None → unreachable deserves an admin ping
                    if previous == "ok":
                        newly_failed.append(server)

            await db.commit()

            for server in newly_failed:
                await _notify_admins_unreachable(db, server)
            if newly_failed:
                await db.commit()

        logger.info("mcp_health_check_done", ok=ok, unreachable=unreachable)
        return {"ok": ok, "unreachable": unreachable, "newly_failed": len(newly_failed)}
    finally:
        await engine.dispose()


async def _probe(server: MCPServer) -> str:
    """Single-server handshake. ``ok`` / ``degraded`` / ``unreachable``."""
    try:
        async def _do():
            async with get_transport(server) as t:
                await t.initialize()

        await asyncio.wait_for(_do(), timeout=HEALTH_CHECK_TIMEOUT)
        return "ok"
    except asyncio.TimeoutError:
        return "unreachable"
    except Exception as e:  # noqa: BLE001
        logger.warning("mcp_probe_failed", server=str(server.id), error=str(e))
        return "degraded"


async def _notify_admins_unreachable(db: AsyncSession, server: MCPServer) -> None:
    """Create a system notification when a server transitions off healthy.

    Best-effort; don't raise — a failed notification must not roll back
    the health_status write.
    """
    try:
        from app.system.models import Notification
        notif = Notification(
            user_id=None,  # broadcast (system notification)
            type="system",
            title="MCP 服务器不可达",
            content=(
                f"MCP 服务器 '{server.name}' 健康检查失败，"
                f"状态: {server.health_status}. 请前往 设置 → MCP 服务器 查看。"
            ),
            priority="high",
            resource_type="mcp_server",
            resource_id=server.id,
        )
        db.add(notif)
        await db.flush()
    except Exception as e:  # noqa: BLE001
        logger.warning("mcp_notify_failed", server=str(server.id), error=str(e))
