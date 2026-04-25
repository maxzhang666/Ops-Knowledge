from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import structlog

from app.core.cache import CacheService
from app.core.database import async_session
from app.knowledge.retrieval.query_rewriter import rewrite_query_v2
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
        rewrite_registry_id: uuid.UUID | None = None,
        rewrite_memory_summary: str | None = None,
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

        # 1. Optional query rewrite (Plan 30 v2 — 启发式 + 结构化输出)
        if rewrite and (rewrite_registry_id or (rewrite_provider_id and rewrite_model_name)):
            r = await rewrite_query_v2(
                query, rewrite_history or [],
                provider_id=rewrite_provider_id,
                model_name=rewrite_model_name,
                registry_id=rewrite_registry_id,
                memory_summary=rewrite_memory_summary,
            )
            query_used = r.query_used
            logger.info(
                "retrieval_query_rewrite",
                original=query, used=r.query_used,
                needs_rewrite=r.needs_rewrite, status=r.status, reason=r.reason,
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

        # 3.5 Plan 32 M3 生命周期 + Plan 29 审批：post-filter 仅在 SQL 侧
        #     表达的可见性约束（归档 / 未通过审批）。
        if results:
            results = await self._filter_invisible(results)

        # 3.6 Plan 36 — Multi-source fusion: 跨 KB 时启用 source weighting +
        #     dedup + MMR diversity（单 KB 跳过，无意义）。
        if results and len(kb_ids) > 1:
            results = await self._apply_fusion(results, kb_ids, top_k=top_k)

        # 4. Optional rerank
        if reranker_provider_id and reranker_model_name and results:
            results = await rerank_results(
                query_used, results, reranker_provider_id, reranker_model_name, top_n=top_k,
            )

        # 5. Increment hit_count + emit governance events (Plan 32 M1.3).
        #    Uses a short dedicated session so retrieval path doesn't couple to caller's tx.
        #    hit_count is a rollup counter (kept for fast queries); the canonical
        #    record is in chunk_usage_events (event_type=hit) for time-window aggregation.
        if results:
            try:
                from sqlalchemy import update
                from app.knowledge.governance.events import record_hits_bulk
                from app.knowledge.models import Chunk
                hit_ids: list[uuid.UUID] = []
                hit_pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
                for r in results:
                    if not r.chunk_id:
                        continue
                    cid = uuid.UUID(r.chunk_id)
                    hit_ids.append(cid)
                    if r.source_kb_id:
                        hit_pairs.append((cid, uuid.UUID(r.source_kb_id)))
                if hit_ids:
                    async with async_session() as hit_db:
                        await hit_db.execute(
                            update(Chunk)
                            .where(Chunk.id.in_(hit_ids))
                            .values(hit_count=Chunk.hit_count + 1)
                        )
                        await record_hits_bulk(hit_db, hit_pairs)
                        await hit_db.commit()
            except Exception:
                logger.debug("hit_count_update_failed", exc_info=True)
        else:
            # No-result path — Plan 32 M1.3 "knowledge gap" data source.
            try:
                from app.knowledge.governance.events import record_no_result
                async with async_session() as gap_db:
                    for kid in kb_ids:
                        await record_no_result(gap_db, kb_id=uuid.UUID(str(kid)), query=query_used)
                    await gap_db.commit()
            except Exception:
                logger.debug("no_result_event_failed", exc_info=True)

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "retrieval_done",
            query=query_used,
            kb_count=len(kb_ids),
            result_count=len(results),
            timing_ms=elapsed,
        )
        # Plan 35 — 记录每次检索（按 query_type）做 auto-tuning 数据底座
        try:
            from app.knowledge.retrieval.query_classifier import classify
            from app.knowledge.retrieval.models import RetrievalLog
            qtype = classify(query_used).type
            async with async_session() as log_db:
                for kid in kb_ids:
                    log_db.add(RetrievalLog(
                        kb_id=uuid.UUID(str(kid)),
                        query=query_used[:500],
                        query_type=qtype,
                        top_k=top_k,
                        result_count=len(results),
                    ))
                await log_db.commit()
        except Exception:
            logger.debug("retrieval_log_write_failed", exc_info=True)
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

    async def _filter_invisible(self, results: list[SearchResult]) -> list[SearchResult]:
        """聚合不可见过滤：归档文档（Plan 32 M3）+ KB.review_required=True
        但 Document.review_status != approved（Plan 29）。失败时保守通过，
        不让治理故障阻断检索。"""
        doc_ids: set[uuid.UUID] = set()
        for r in results:
            if r.document_id:
                try:
                    doc_ids.add(uuid.UUID(r.document_id))
                except Exception:
                    continue
        if not doc_ids:
            return results
        try:
            from sqlalchemy import select as _select
            from app.knowledge.models import Document, KnowledgeBase
            async with async_session() as db:
                rows = (await db.execute(
                    _select(
                        Document.id,
                        Document.is_archived,
                        Document.review_status,
                        KnowledgeBase.review_required,
                    )
                    .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
                    .where(Document.id.in_(doc_ids))
                )).all()
            invisible: set[str] = set()
            for did, archived, review_status, review_required in rows:
                if archived:
                    invisible.add(str(did))
                    continue
                if review_required and review_status != "approved":
                    invisible.add(str(did))
            if invisible:
                filtered = [r for r in results if r.document_id not in invisible]
                logger.debug(
                    "retrieval_invisible_filtered",
                    dropped=len(results) - len(filtered),
                )
                return filtered
            return results
        except Exception:
            logger.debug("retrieval_invisible_filter_failed", exc_info=True)
            return results

    async def _apply_fusion(
        self, results: list[SearchResult], kb_ids: list[str], *, top_k: int,
    ) -> list[SearchResult]:
        """Plan 36 — 跨 KB 智能融合：源权重 + 去重 + MMR 多样性。"""
        try:
            from sqlalchemy import select as _select
            from app.knowledge.coverage.models import ChunkCrossKBRedundancyPair
            from app.knowledge.governance.service import GovernanceService
            from app.knowledge.retrieval.fusion import (
                FusionConfig, fuse_results, health_to_weight,
            )

            # 1) source weights = 健康分派生
            source_weights: dict[str, float] = {}
            try:
                async with async_session() as gov_db:
                    svc = GovernanceService(gov_db)
                    for kid in kb_ids:
                        try:
                            health = await svc.compute_health(uuid.UUID(str(kid)))
                            source_weights[str(kid)] = health_to_weight(health.health_score)
                        except Exception:
                            source_weights[str(kid)] = 1.0
            except Exception:
                logger.debug("fusion_health_lookup_failed", exc_info=True)

            # 2) cross-KB dedup pairs（仅查涉及到的 chunk）
            dedup_pairs: list[tuple[str, str]] = []
            chunk_ids = {r.chunk_id for r in results if r.chunk_id}
            if len(chunk_ids) > 1:
                async with async_session() as dd_db:
                    rows = (await dd_db.execute(
                        _select(
                            ChunkCrossKBRedundancyPair.chunk_a_id,
                            ChunkCrossKBRedundancyPair.chunk_b_id,
                        ).where(
                            ChunkCrossKBRedundancyPair.chunk_a_id.in_(
                                [uuid.UUID(c) for c in chunk_ids]
                            ),
                            ChunkCrossKBRedundancyPair.chunk_b_id.in_(
                                [uuid.UUID(c) for c in chunk_ids]
                            ),
                        )
                    )).all()
                    dedup_pairs = [(str(a), str(b)) for a, b in rows]

            return fuse_results(
                results,
                source_weights=source_weights,
                dedup_pairs=dedup_pairs,
                top_k=top_k,
                config=FusionConfig(),
            )
        except Exception:
            logger.debug("fusion_failed", exc_info=True)
            return results
