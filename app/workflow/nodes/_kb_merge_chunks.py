"""KB Merge Chunks node (Plan 27 M5) — 简化版 redundancy 合并建议。

Input:
  * chunk_a_id, chunk_b_id (UUID string)  —— 两个高相似 chunk
  * keep (str: "a" | "b" | "both")        —— 合并策略；"a"/"b" 归档另一侧所在 chunk 的文档，"both" 只做通知

真正的语义合并涉及：
  * chunk 内容合并（拼接 / LLM 总结）
  * 引用关系迁移（会话 metadata 中的 chunk_id 重指）
  * 向量重算
这里 v1 只做"归档被合并方所在文档"的保守动作；语义合并由人工在治理页发起后续流程。
"""
from __future__ import annotations

import uuid
from typing import Literal

from app.workflow.nodes.base import (
    AbstractNode, NodeConfigForm, NodeContext, NodeIO, NodeManifest, NodeResult,
)


class KBMergeChunksNode(AbstractNode):
    manifest = NodeManifest(
        type="kb_merge_chunks",
        category="extension",
        name="合并冗余切片",
        description="对两个高相似切片的合并动作：归档被合并方所在文档",
    )
    io = NodeIO(
        inputs={
            "chunk_a_id": {"type": "string"},
            "chunk_b_id": {"type": "string"},
            "keep": {"type": "string"},
        },
        outputs={
            "kept_chunk_id": {"type": "string"},
            "archived_document_ids": {"type": "array"},
        },
    )
    config_form = NodeConfigForm(schema={
        "type": "object",
        "properties": {
            "default_keep": {"type": "string", "enum": ["a", "b", "both"], "default": "both"},
        },
    })

    async def validate(self, ctx: NodeContext) -> None:
        if "chunk_a_id" not in ctx.inputs or "chunk_b_id" not in ctx.inputs:
            raise ValueError("kb_merge_chunks: 'chunk_a_id' and 'chunk_b_id' are required")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.core.config import settings
        from app.knowledge.models import Chunk, Document

        a = uuid.UUID(str(ctx.inputs["chunk_a_id"]))
        b = uuid.UUID(str(ctx.inputs["chunk_b_id"]))
        keep: Literal["a", "b", "both"] = (
            ctx.inputs.get("keep") or ctx.config.get("default_keep") or "both"
        )
        if keep not in ("a", "b", "both"):
            raise ValueError(f"kb_merge_chunks: invalid keep '{keep}'")

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        archived_doc_ids: list[str] = []
        try:
            async with sm() as db:
                chunk_a = await db.get(Chunk, a)
                chunk_b = await db.get(Chunk, b)
                if chunk_a is None or chunk_b is None:
                    raise ValueError("kb_merge_chunks: one or both chunks not found")

                kept_chunk_id = str(a) if keep != "b" else str(b)
                to_archive_doc_ids: list[uuid.UUID] = []
                if keep == "a" and chunk_a.document_id != chunk_b.document_id:
                    to_archive_doc_ids.append(chunk_b.document_id)
                elif keep == "b" and chunk_a.document_id != chunk_b.document_id:
                    to_archive_doc_ids.append(chunk_a.document_id)

                for doc_id in to_archive_doc_ids:
                    doc = await db.get(Document, doc_id)
                    if doc and not doc.is_archived:
                        doc.is_archived = True
                        archived_doc_ids.append(str(doc_id))
                await db.commit()

                return NodeResult(outputs={
                    "kept_chunk_id": kept_chunk_id,
                    "archived_document_ids": archived_doc_ids,
                })
        finally:
            await engine.dispose()
