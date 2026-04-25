"""Governance event → Workflow trigger bridge (Plan 27 M2).

监听 event_bus 的 ``governance.alert`` 事件，根据 workflow 的 trigger
配置匹配并启动执行。

Workflow 参与方式：
  * ``workflows.trigger_type == "governance_event"``
  * ``workflows.graph_data.trigger_config`` (dict)：
      - ``kinds``  : list[str]    告警种类白名单；空或缺省 = 接受所有
      - ``kb_ids`` : list[str]    KB 白名单；空或缺省 = 接受所有
      - ``severities``: list[str] 严重度白名单；空或缺省 = 接受所有

匹配成功：创建 WorkflowExecution，``trigger_input`` = alert data
(``{kb_id, kind, severity, count, title, preview, kb_name}``)。
执行通过 ``run_and_persist`` 异步后台跑，handler 不阻塞 bus。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.integration.event_bus import on
from app.integration.events import Event
from app.workflow.execution_service import ExecutionService
from app.workflow.events import EventBus
from app.workflow.models import Workflow

logger = structlog.get_logger(__name__)

TRIGGER_TYPE = "governance_event"


@on("governance.alert")
async def handle_governance_alert(event: Event) -> None:
    """bus subscriber 调用。找到匹配 workflow 并并发启动。"""
    data = event.data or {}
    kind = str(data.get("kind") or "")
    kb_id = str(data.get("kb_id") or "")
    severity = str(data.get("severity") or "")
    if not kind or not kb_id:
        return

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sm() as db:
            rows = (await db.execute(
                select(Workflow).where(
                    Workflow.trigger_type == TRIGGER_TYPE,
                    Workflow.status == "published",
                )
            )).scalars().all()

        matched = [w for w in rows if _matches(w, kind=kind, kb_id=kb_id, severity=severity)]
        if not matched:
            return

        logger.info(
            "governance_workflow_matched",
            kind=kind, kb_id=kb_id, count=len(matched),
        )
        # 并发启动；单个失败不影响其他
        await asyncio.gather(
            *[_launch(w.id, data) for w in matched],
            return_exceptions=True,
        )
    finally:
        await engine.dispose()


def _matches(
    wf: Workflow, *, kind: str, kb_id: str, severity: str,
) -> bool:
    cfg = (wf.graph_data or {}).get("trigger_config") or {}
    if not isinstance(cfg, dict):
        return False
    kinds = cfg.get("kinds") or []
    if kinds and kind not in kinds:
        return False
    kb_ids = cfg.get("kb_ids") or []
    if kb_ids and kb_id not in [str(x) for x in kb_ids]:
        return False
    severities = cfg.get("severities") or []
    if severities and severity not in severities:
        return False
    return True


async def _launch(workflow_id: uuid.UUID, trigger_input: dict[str, Any]) -> None:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sm() as db:
            svc = ExecutionService(db)
            execution = await svc.create_execution(
                workflow_id, user_id=None, trigger_input=trigger_input,
            )
            await db.commit()
            bus = EventBus()
            await svc.run_and_persist(execution, bus)
            await db.commit()
    except Exception as exc:
        logger.warning(
            "governance_workflow_launch_failed",
            workflow_id=str(workflow_id), error=str(exc)[:200],
        )
    finally:
        await engine.dispose()
