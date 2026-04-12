import uuid

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.knowledge.models import Chunk

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

    async def list_chunks(
        self,
        kb_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Chunk], int]:
        base = select(Chunk).where(Chunk.knowledge_base_id == kb_id)
        if document_id is not None:
            base = base.where(Chunk.document_id == document_id)

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
        result = await self.db.execute(
            delete(Chunk).where(Chunk.document_id == document_id)
        )
        await self.db.flush()
        return result.rowcount
