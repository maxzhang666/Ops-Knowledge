"""Entry 批量导入 celery task — Plan 41 M3.1。

支持 CSV 和 JSONL 两种格式。每行解析为 {title, content, tags?} 后
逐行调用 EntrySourcePlugin.create_unit + chunk_service 持久化 + 触发
embedding（让 entry KB 真正可检索）。

错误隔离：单行解析失败不阻塞其他行；最终汇总成功 / 失败 / skipped 数。
"""
from __future__ import annotations

import csv
import io
import json
import uuid

import structlog
from celery import shared_task
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings

logger = structlog.get_logger(__name__)


def _get_sync_engine():
    return create_engine(settings.DATABASE_URL.replace("+asyncpg", "+psycopg"), pool_pre_ping=True)


@shared_task(
    name="app.knowledge.sources.entry_tasks.import_entries_batch",
    bind=True, max_retries=2, default_retry_delay=30,
)
def import_entries_batch(
    self,
    kb_id: str,
    author_id: str,
    file_format: str,         # "csv" | "jsonl"
    file_content_b64: str,    # base64 编码的文件内容（避免大文本作为 celery arg）
) -> dict:
    """异步批量导入。celery worker 进程独立解析文件，逐行入库。"""
    import asyncio
    import base64

    return asyncio.run(_run_import(
        kb_id=uuid.UUID(kb_id),
        author_id=uuid.UUID(author_id),
        file_format=file_format,
        file_bytes=base64.b64decode(file_content_b64),
    ))


async def _run_import(
    *,
    kb_id: uuid.UUID,
    author_id: uuid.UUID,
    file_format: str,
    file_bytes: bytes,
) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.knowledge.chunk_service import ChunkService
    from app.knowledge.embedding.tasks import embed_unit_chunks
    from app.knowledge.models import KnowledgeBase
    from app.knowledge.sources import get_plugin
    from app.core.tasks import safe_delay

    rows = _parse_rows(file_bytes, file_format)
    if not rows:
        return {"status": "empty", "imported": 0, "failed": 0}

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    imported = 0
    failed = 0
    errors: list[dict] = []
    created_unit_ids: list[uuid.UUID] = []

    try:
        async with sm() as db:
            kb = await db.get(KnowledgeBase, kb_id)
            if kb is None or kb.source_type != "entry":
                return {"status": "error", "message": "KB not found or not entry-type"}

            plugin = get_plugin("entry")
            chunk_svc = ChunkService(db)

            for idx, row in enumerate(rows):
                try:
                    title = (row.get("title") or "").strip()
                    content = (row.get("content") or "").strip()
                    if not title or not content:
                        failed += 1
                        errors.append({"row": idx + 1, "error": "missing title or content"})
                        continue
                    tags = row.get("tags")
                    if isinstance(tags, str):
                        # CSV 场景：tags 用 ; 或 , 分隔
                        tags = [t.strip() for t in tags.replace(";", ",").split(",") if t.strip()]
                    payload = {
                        "title": title[:200],
                        "content": content,
                        "tags": tags if isinstance(tags, list) else None,
                        "author_id": author_id,
                    }
                    view = await plugin.create_unit(db, kb_id, payload)
                    await chunk_svc.create_chunks_for_unit("entry", view.unit_id, kb_id)
                    created_unit_ids.append(view.unit_id)
                    imported += 1
                except Exception as exc:
                    failed += 1
                    errors.append({"row": idx + 1, "error": str(exc)[:200]})
                    logger.debug("import_row_failed", idx=idx, exc_info=True)

            await db.commit()

        # 提交后批量 enqueue embedding（每个 entry 独立 task）
        for unit_id in created_unit_ids:
            try:
                safe_delay(embed_unit_chunks, "entry", str(unit_id), str(kb_id))
            except Exception:
                logger.debug("embed_enqueue_failed", unit_id=str(unit_id), exc_info=True)
    finally:
        await engine.dispose()

    logger.info(
        "import_entries_batch_done",
        kb_id=str(kb_id), imported=imported, failed=failed,
    )
    return {
        "status": "completed",
        "imported": imported,
        "failed": failed,
        "errors": errors[:50],  # 截断避免 result 过大
    }


def _parse_rows(content: bytes, file_format: str) -> list[dict]:
    """容错解析：失败抛 ValueError；单行错误由调用方处理。"""
    text = content.decode("utf-8", errors="replace")
    if file_format == "csv":
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)
    if file_format == "jsonl":
        rows: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows
    raise ValueError(f"unsupported format: {file_format}")
