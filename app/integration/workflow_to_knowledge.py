"""Workflow → Knowledge facade. Any workflow-side code that needs to touch
knowledge MUST go through this module, not through app.knowledge.* directly.
Keeps the dependency graph strictly layered and provides a single place to
evolve cross-domain contracts.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


async def retrieve(
    db: AsyncSession,
    *,
    query: str,
    kb_ids: list[str],
    top_k: int = 10,
    folder_ids: list[str] | None = None,
    score_threshold: float = 0.0,
    rewrite: bool = False,
) -> list[dict[str, Any]]:
    """Unified retrieval entry point for workflow nodes. Returns simplified
    chunk dicts — upstream SearchResult shape is not leaked across the boundary."""
    from app.knowledge.retrieval.service import RetrievalService
    from app.knowledge.service import KBService

    kb_svc = KBService(db)
    first_kb = await kb_svc.get_kb(uuid.UUID(kb_ids[0]))
    if not first_kb.embedding_provider_id:
        raise RuntimeError("KB has no embedding provider configured")

    retrieval = RetrievalService()
    result = await retrieval.retrieve(
        query=query,
        kb_ids=kb_ids,
        embedding_provider_id=first_kb.embedding_provider_id,
        embedding_model_name=first_kb.embedding_model_name,
        top_k=top_k,
        folder_ids=folder_ids,
        rewrite=rewrite,
    )
    return [
        {
            "id": r.chunk_id,
            "content": r.content,
            "score": r.score,
            "document_id": r.document_id,
            "document_title": r.title,
            "folder_id": r.folder_id,
            "level": r.level,
            "source_kb_id": r.source_kb_id,
        }
        for r in result.results
        if r.score >= score_threshold
    ]


async def get_kb_summary(db: AsyncSession, kb_id: uuid.UUID) -> dict:
    """Minimal metadata for compound workflows (e.g. preflight validation)."""
    from app.knowledge.service import KBService
    kb = await KBService(db).get_kb(kb_id)
    return {
        "id": str(kb.id),
        "name": kb.name,
        "embedding_provider_id": (
            str(kb.embedding_provider_id) if kb.embedding_provider_id else None
        ),
        "embedding_model_name": kb.embedding_model_name,
        "chunk_count": kb.chunk_count,
        "status": kb.status.value if hasattr(kb.status, "value") else str(kb.status),
    }
