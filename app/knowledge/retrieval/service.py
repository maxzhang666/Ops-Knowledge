from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import structlog

from app.core.database import async_session
from app.knowledge.retrieval.query_rewriter import rewrite_query
from app.knowledge.retrieval.reranker import rerank_results
from app.knowledge.retrieval.searcher import HybridSearcher, SearchResult
from app.model.service import ModelService

logger = structlog.get_logger(__name__)


@dataclass
class RetrievalResult:
    results: list[SearchResult] = field(default_factory=list)
    query_used: str = ""
    timing_ms: int = 0
    total_searched: int = 0


class RetrievalService:
    def __init__(self, searcher: HybridSearcher | None = None):
        self._searcher = searcher or HybridSearcher()

    async def retrieve(
        self,
        query: str,
        kb_ids: list[str],
        embedding_provider_id: uuid.UUID,
        embedding_model_name: str,
        top_k: int = 10,
        folder_ids: list[str] | None = None,
        rewrite: bool = False,
        rewrite_history: list[dict] | None = None,
        rewrite_provider_id: uuid.UUID | None = None,
        rewrite_model_name: str | None = None,
        reranker_provider_id: uuid.UUID | None = None,
        reranker_model_name: str | None = None,
    ) -> RetrievalResult:
        t0 = time.monotonic()
        query_used = query

        # 1. Optional query rewrite
        if rewrite and rewrite_provider_id and rewrite_model_name:
            query_used = await rewrite_query(
                query, rewrite_history or [], rewrite_provider_id, rewrite_model_name,
            )

        # 2. Embed query
        async with async_session() as session:
            model_svc = ModelService(session)
            vectors = await model_svc.embed(embedding_provider_id, embedding_model_name, [query_used])
        query_vector = vectors[0]

        # 3. Multi-KB search
        kb_configs = [{"collection_name": f"kb_{kb_id}", "kb_id": kb_id} for kb_id in kb_ids]
        results = await self._searcher.multi_kb_search(
            kb_configs, query_vector, query_used, top_k=top_k, folder_ids=folder_ids,
        )
        total_searched = len(results)

        # 4. Optional rerank
        if reranker_provider_id and reranker_model_name and results:
            results = await rerank_results(
                query_used, results, reranker_provider_id, reranker_model_name, top_n=top_k,
            )

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "retrieval_done",
            query=query_used,
            kb_count=len(kb_ids),
            result_count=len(results),
            timing_ms=elapsed,
        )
        return RetrievalResult(
            results=results,
            query_used=query_used,
            timing_ms=elapsed,
            total_searched=total_searched,
        )
