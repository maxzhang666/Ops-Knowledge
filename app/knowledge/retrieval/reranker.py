from __future__ import annotations

import uuid

import structlog

from app.core.database import async_session
from app.knowledge.retrieval.searcher import SearchResult
from app.model.service import ModelService

logger = structlog.get_logger(__name__)


async def rerank_results(
    query: str,
    results: list[SearchResult],
    provider_id: uuid.UUID,
    model_name: str,
    top_n: int | None = None,
) -> list[SearchResult]:
    if not results:
        return results

    try:
        async with async_session() as session:
            svc = ModelService(session)
            documents = [r.content for r in results]
            ranked = await svc.rerank(provider_id, model_name, query, documents, top_n=top_n)

        reranked: list[SearchResult] = []
        for item in ranked:
            idx = item["index"]
            r = results[idx]
            r.score = item["relevance_score"]
            reranked.append(r)

        reranked.sort(key=lambda r: r.score, reverse=True)
        logger.info("rerank_done", input_count=len(results), output_count=len(reranked))
        return reranked
    except Exception:
        logger.warning("rerank_failed", exc_info=True)
        return results
