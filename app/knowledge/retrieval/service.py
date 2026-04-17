from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import structlog

from app.core.cache import CacheService
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
    def __init__(self, searcher: HybridSearcher | None = None, cache: CacheService | None = None):
        self._searcher = searcher or HybridSearcher()
        self._cache = cache or CacheService()

    async def retrieve(
        self,
        query: str,
        kb_ids: list[str],
        embedding_provider_id: uuid.UUID | None = None,
        embedding_model_name: str | None = None,
        top_k: int = 10,
        folder_ids: list[str] | None = None,
        rewrite: bool = False,
        rewrite_history: list[dict] | None = None,
        rewrite_provider_id: uuid.UUID | None = None,
        rewrite_model_name: str | None = None,
        reranker_provider_id: uuid.UUID | None = None,
        reranker_model_name: str | None = None,
        embedding_model_registry_id: uuid.UUID | None = None,
    ) -> RetrievalResult:
        t0 = time.monotonic()
        query_used = query

        # L2 cache lookup — include embedding config so changing model invalidates cache
        emb_key = (
            f"reg:{embedding_model_registry_id}"
            if embedding_model_registry_id
            else f"prov:{embedding_provider_id}:{embedding_model_name or ''}"
        )
        cache_key_parts = (
            ",".join(sorted(kb_ids)), query, str(top_k),
            ",".join(sorted(folder_ids or [])), str(reranker_model_name or ""),
            emb_key,
        )
        try:
            cached = await self._cache.get_retrieval(*cache_key_parts)
            if cached:
                logger.info("retrieval_cache_hit", query=query)
                return RetrievalResult(
                    results=[SearchResult(**r) for r in cached["results"]],
                    query_used=cached["query_used"],
                    timing_ms=0,
                    total_searched=cached["total_searched"],
                )
        except Exception:
            pass  # cache miss or error, proceed normally

        # 1. Optional query rewrite
        if rewrite and rewrite_provider_id and rewrite_model_name:
            query_used = await rewrite_query(
                query, rewrite_history or [], rewrite_provider_id, rewrite_model_name,
            )

        # 2. Embed query
        # TODO: Multi-KB with different embedding models is not yet supported.
        #       Currently all KBs in a single retrieval call share one embedding
        #       config (from the first KB). A full fix requires per-KB embedding
        #       and searching each KB with its own model, then merging results.
        async with async_session() as session:
            model_svc = ModelService(session)
            if embedding_model_registry_id:
                vectors = await model_svc.embed_by_registry(embedding_model_registry_id, [query_used])
            elif embedding_provider_id and embedding_model_name:
                vectors = await model_svc.embed(embedding_provider_id, embedding_model_name, [query_used])
            else:
                raise ValueError("No embedding config: provide registry_id or provider_id+model_name")
        query_vector = vectors[0]

        # 3. Multi-KB search
        kb_configs = [{"collection_name": f"kb_{kb_id}", "kb_id": kb_id} for kb_id in kb_ids]
        try:
            results = await self._searcher.multi_kb_search(
                kb_configs, query_vector, query_used, top_k=top_k, folder_ids=folder_ids,
            )
        finally:
            try:
                self._searcher._milvus.close()
            except Exception:
                pass
        total_searched = len(results)

        # 4. Optional rerank
        if reranker_provider_id and reranker_model_name and results:
            results = await rerank_results(
                query_used, results, reranker_provider_id, reranker_model_name, top_n=top_k,
            )

        # 5. Increment hit_count for actual returned chunks (best-effort, non-blocking failure).
        #    Uses a short dedicated session so retrieval path doesn't couple to caller's tx.
        if results:
            try:
                from sqlalchemy import update
                from app.knowledge.models import Chunk
                hit_ids = [uuid.UUID(r.chunk_id) for r in results if r.chunk_id]
                if hit_ids:
                    async with async_session() as hit_db:
                        await hit_db.execute(
                            update(Chunk)
                            .where(Chunk.id.in_(hit_ids))
                            .values(hit_count=Chunk.hit_count + 1)
                        )
                        await hit_db.commit()
            except Exception:
                logger.debug("hit_count_update_failed", exc_info=True)

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "retrieval_done",
            query=query_used,
            kb_count=len(kb_ids),
            result_count=len(results),
            timing_ms=elapsed,
        )
        # L2 cache store
        try:
            from dataclasses import asdict
            await self._cache.set_retrieval(
                {"results": [asdict(r) for r in results], "query_used": query_used, "total_searched": total_searched},
                *cache_key_parts,
            )
        except Exception:
            pass

        return RetrievalResult(
            results=results,
            query_used=query_used,
            timing_ms=elapsed,
            total_searched=total_searched,
        )
