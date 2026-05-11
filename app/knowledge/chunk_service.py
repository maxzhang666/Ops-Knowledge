import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.knowledge.milvus.service import MilvusService, kb_collection_name
from app.knowledge.models import Chunk
from app.knowledge.quality.scorer import score_chunk

logger = structlog.get_logger(__name__)


class ChunkService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        self.db.add_all(chunks)
        await self.db.flush()
        return chunks

    async def get_chunk(self, chunk_id: uuid.UUID) -> Chunk:
        chunk = await self.db.get(Chunk, chunk_id)
        if chunk is None:
            raise NotFoundError("Chunk", str(chunk_id))
        return chunk

    async def create_chunks_for_unit(
        self,
        unit_type: str,
        unit_id: uuid.UUID,
        kb_id: uuid.UUID,
    ) -> int:
        """Plan 41 — 通过 IngestionPlugin.to_chunk_seeds 产出 chunks，统一持久化。
        embedding 由后续 unit-aware 任务接管（vector_id 暂为 None）。
        返回创建的 chunks 数量。"""
        from app.knowledge.sources import get_plugin
        from app.knowledge.models import KnowledgeBase, KnowledgeEntry

        kb = await self.db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise NotFoundError("KnowledgeBase", str(kb_id))
        plugin = get_plugin(kb.source_type)

        # 取 unit 实例（多态：按 source_type 决定从哪张表取）
        if unit_type == "entry":
            unit = await self.db.get(KnowledgeEntry, unit_id)
        elif unit_type == "document":
            from app.knowledge.models import Document
            unit = await self.db.get(Document, unit_id)
        else:
            raise ValidationError(f"Unsupported unit_type: {unit_type}")
        if unit is None:
            raise NotFoundError(f"Unit({unit_type})", str(unit_id))

        seeds = await plugin.to_chunk_seeds(self.db, unit)
        if not seeds:
            return 0

        # Plan 39 — chunks.review_excluded 跟随 unit.review_status
        review_excluded = (
            getattr(unit, "review_status", None) in ("pending", "rejected")
        )

        chunks = [
            Chunk(
                unit_type=unit_type,
                unit_id=unit_id,
                knowledge_base_id=kb_id,
                folder_id=seed.folder_id,
                content=seed.content,
                parent_chunk_id=seed.parent_chunk_id,
                level=seed.level,
                position=seed.position,
                token_count=seed.token_count,
                quality_score=score_chunk(seed.content),
                metadata_=seed.metadata,
                review_excluded=review_excluded,
            )
            for seed in seeds
        ]
        self.db.add_all(chunks)
        await self.db.flush()
        return len(chunks)

    async def list_chunks(
        self,
        kb_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Chunk], int]:
        base = select(Chunk).where(Chunk.knowledge_base_id == kb_id)
        if document_id is not None:
            # Plan 40 M2 — 多态 unit FK 切读
            base = base.where(
                Chunk.unit_type == "document", Chunk.unit_id == document_id,
            )

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        rows = await self.db.scalars(
            base.order_by(Chunk.position).offset(offset).limit(limit)
        )
        return list(rows.all()), total

    async def count_chunks(self, kb_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(Chunk.knowledge_base_id == kb_id)
        return (await self.db.execute(stmt)).scalar() or 0

    async def delete_chunks_by_document(self, document_id: uuid.UUID) -> int:
        # Plan 40 M2 — 多态 unit FK 切读
        result = await self.db.execute(
            delete(Chunk).where(
                Chunk.unit_type == "document", Chunk.unit_id == document_id,
            )
        )
        await self.db.flush()
        return result.rowcount

    # ── Editing operations ──────────────────────────────────────

    async def edit_chunk(
        self, chunk_id: uuid.UUID, new_content: str, user_id: uuid.UUID,
    ) -> Chunk:
        chunk = await self.get_chunk(chunk_id)
        history = chunk.edit_history or []
        history.append({
            "user_id": str(user_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "previous_content": chunk.content,
        })

        chunk.content = new_content
        chunk.is_manually_edited = True
        chunk.edit_history = history
        chunk.vector_id = None
        chunk.token_count = len(new_content.split())
        chunk.quality_score = score_chunk(new_content)
        await self.db.flush()
        return chunk

    async def preview_split(
        self, chunk_id: uuid.UUID, split_positions: list[int],
    ) -> list[dict]:
        """Preview split result without persistence — returns per-segment content and token count."""
        chunk = await self.get_chunk(chunk_id)
        content = chunk.content
        positions = sorted(set(split_positions))

        if not positions or any(p <= 0 or p >= len(content) for p in positions):
            raise ValidationError("Invalid split positions")

        boundaries = [0, *positions, len(content)]
        segments = [content[boundaries[i]:boundaries[i + 1]] for i in range(len(boundaries) - 1)]
        return [{"content": s, "token_count": len(s.split())} for s in segments]

    async def split_chunk(
        self, chunk_id: uuid.UUID, split_positions: list[int], user_id: uuid.UUID,
    ) -> list[Chunk]:
        chunk = await self.get_chunk(chunk_id)
        content = chunk.content
        positions = sorted(set(split_positions))

        if not positions or any(p <= 0 or p >= len(content) for p in positions):
            raise ValidationError("Invalid split positions")

        boundaries = [0, *positions, len(content)]
        segments = [content[boundaries[i]:boundaries[i + 1]] for i in range(len(boundaries) - 1)]

        new_chunks: list[Chunk] = []
        for i, seg in enumerate(segments):
            new_chunks.append(Chunk(
                # Plan 40 M3 — document_id 已 drop
                unit_type=chunk.unit_type,
                unit_id=chunk.unit_id,
                knowledge_base_id=chunk.knowledge_base_id,
                folder_id=chunk.folder_id,
                content=seg,
                parent_chunk_id=chunk.parent_chunk_id,
                level=chunk.level,
                position=chunk.position + i,
                token_count=len(seg.split()),
                quality_score=score_chunk(seg),
                is_manually_edited=True,
                # Plan 39 — 继承父 chunk 的 review_excluded（split 不改 review_status）
                review_excluded=chunk.review_excluded,
                edit_history=[{
                    "user_id": str(user_id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "split",
                    "source_chunk_id": str(chunk_id),
                }],
            ))

        self.db.add_all(new_chunks)
        await self.db.delete(chunk)
        await self.db.flush()
        for c in new_chunks:
            await self.db.refresh(c)
        return new_chunks

    async def merge_chunks(
        self, chunk_ids: list[uuid.UUID], user_id: uuid.UUID,
    ) -> Chunk:
        if len(chunk_ids) < 2:
            raise ValidationError("At least 2 chunks required to merge")

        chunks: list[Chunk] = []
        for cid in chunk_ids:
            chunks.append(await self.get_chunk(cid))

        # Verify all from same unit (Plan 40 M3 多态 FK)
        unit_keys = {(c.unit_type, c.unit_id) for c in chunks}
        if len(unit_keys) > 1:
            raise ValidationError("All chunks must belong to the same unit")

        chunks.sort(key=lambda c: c.position)
        merged_content = "\n\n".join(c.content for c in chunks)

        merged = Chunk(
            # Plan 40 M3 — document_id 已 drop
            unit_type=chunks[0].unit_type,
            unit_id=chunks[0].unit_id,
            knowledge_base_id=chunks[0].knowledge_base_id,
            folder_id=chunks[0].folder_id,
            content=merged_content,
            parent_chunk_id=chunks[0].parent_chunk_id,
            level=chunks[0].level,
            position=chunks[0].position,
            token_count=len(merged_content.split()),
            quality_score=score_chunk(merged_content),
            is_manually_edited=True,
            # Plan 39 — 任一 source 为 excluded 则合并 chunk 也 excluded（保守）
            review_excluded=any(c.review_excluded for c in chunks),
            edit_history=[{
                "user_id": str(user_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "merge",
                "source_chunk_ids": [str(cid) for cid in chunk_ids],
            }],
        )
        self.db.add(merged)
        for c in chunks:
            await self.db.delete(c)
        await self.db.flush()
        await self.db.refresh(merged)
        return merged

    async def delete_chunk(self, chunk_id: uuid.UUID) -> None:
        chunk = await self.get_chunk(chunk_id)
        if chunk.vector_id:
            try:
                milvus = MilvusService()
                collection = kb_collection_name(chunk.knowledge_base_id)
                milvus.delete_by_ids(collection, [chunk.vector_id])
            except Exception:
                logger.warning("milvus_delete_failed", chunk_id=str(chunk_id), exc_info=True)
        await self.db.delete(chunk)
        await self.db.flush()

    async def annotate_chunk(
        self, chunk_id: uuid.UUID, tags: list[str] | None = None, notes: str | None = None,
    ) -> Chunk:
        chunk = await self.get_chunk(chunk_id)
        meta = chunk.metadata_ or {}
        if tags is not None:
            meta["tags"] = tags
        if notes is not None:
            meta["notes"] = notes
        chunk.metadata_ = meta
        await self.db.flush()
        return chunk
