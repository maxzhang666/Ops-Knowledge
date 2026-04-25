"""KB Archive Document node (Plan 27 M5).

用于 stale-doc-review 之类的治理 Workflow：审批通过后归档文档。

Input:
  * document_id (UUID string) —— 必填
  * archive (bool)            —— 默认 True；False 表示恢复

Output:
  * document_id, is_archived
"""
from __future__ import annotations

import uuid

from app.workflow.nodes.base import (
    AbstractNode, NodeConfigForm, NodeContext, NodeIO, NodeManifest, NodeResult,
)


class KBArchiveDocumentNode(AbstractNode):
    manifest = NodeManifest(
        type="kb_archive_document",
        category="extension",
        name="归档文档",
        description="对指定文档执行归档/恢复（治理 Workflow 动作节点）",
    )
    io = NodeIO(
        inputs={
            "document_id": {"type": "string"},
            "archive": {"type": "boolean"},
        },
        outputs={
            "document_id": {"type": "string"},
            "is_archived": {"type": "boolean"},
        },
    )
    config_form = NodeConfigForm(schema={
        "type": "object",
        "properties": {
            "archive": {"type": "boolean", "default": True},
        },
    })

    async def validate(self, ctx: NodeContext) -> None:
        if "document_id" not in ctx.inputs:
            raise ValueError("kb_archive_document: 'document_id' input is required")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.core.config import settings
        from app.knowledge.models import Document

        doc_id_raw = ctx.inputs.get("document_id")
        archive_flag = ctx.inputs.get("archive")
        if archive_flag is None:
            archive_flag = bool(ctx.config.get("archive", True))
        else:
            archive_flag = bool(archive_flag)

        doc_id = uuid.UUID(str(doc_id_raw))

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with sm() as db:
                doc = await db.get(Document, doc_id)
                if doc is None:
                    raise ValueError(f"Document {doc_id} not found")
                doc.is_archived = archive_flag
                if not archive_flag:
                    doc.is_stale = False
                    doc.stale_since = None
                await db.commit()
                return NodeResult(outputs={
                    "document_id": str(doc_id),
                    "is_archived": archive_flag,
                })
        finally:
            await engine.dispose()
