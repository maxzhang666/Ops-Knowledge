from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import structlog

from app.core.cache import CacheService
from app.core.database import async_session
from app.knowledge.milvus.service import kb_collection_name
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
        # Workbench M1.3 — exposed retrieval knobs + auth context for log replay
        bm25_weight: float = 1.0,
        vector_weight: float = 1.0,
        score_threshold: float | None = None,
        created_by: uuid.UUID | None = None,
        # M6.5 — 测试标志：True 时跳过治理事件（hit_count / record_hits_bulk /
        # record_no_result），retrieval_logs 仍写入但带 is_test=True，让 Workbench
        # 历史侧栏可见，治理统计可过滤
        is_test: bool = False,
        # Spec 25 L2 — tag pre-filter；{any_of, all_of, not} 三键任组合
        tag_filter: dict | None = None,
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
        kb_configs = [{"collection_name": kb_collection_name(kb_id), "kb_id": kb_id} for kb_id in kb_ids]

        # Spec 25 L4 — 按 KB tag_settings 决定每 KB 的 boost_weight + canonical embeddings；
        # 任一 KB 不可用直接 noop（无 settings / disabled / 字典为空 / embed 失败均退化为不 boost）
        max_boost_weight = 0.0
        canonical_embeddings_by_kb: dict[str, dict[str, list[float]]] = {}
        try:
            from app.knowledge.tagging.canonical_cache import (
                get_kb_canonical_embeddings,
            )
            from app.knowledge.tagging.models import KBTagSettings
            async with async_session() as boost_session:
                boost_model_svc = ModelService(boost_session)
                for kb_id_str in kb_ids:
                    row = await boost_session.get(KBTagSettings, uuid.UUID(kb_id_str))
                    if row is None or row.tag_boost_weight <= 0:
                        continue
                    emb = await get_kb_canonical_embeddings(
                        boost_session, uuid.UUID(kb_id_str), boost_model_svc,
                    )
                    if emb:
                        canonical_embeddings_by_kb[kb_id_str] = emb
                        if row.tag_boost_weight > max_boost_weight:
                            max_boost_weight = row.tag_boost_weight
        except Exception:
            logger.warning("tag_boost_setup_failed", exc_info=True)

        try:
            results = await self._searcher.multi_kb_search(
                kb_configs, query_vector, query_used,
                top_k=top_k, folder_ids=folder_ids,
                bm25_weight=bm25_weight, vector_weight=vector_weight,
                tag_filter=tag_filter,
                tag_boost_weight=max_boost_weight,
                canonical_embeddings_by_kb=canonical_embeddings_by_kb,
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

        # 4.5 Optional 最低向量相关度 filter — 阈值作用于 `dense_score`（cosine 0-1，
        # 跨 query/KB 一致），而不是融合分（RRF 量级 ~1/K，不是相关度）。仅命中
        # BM25 的 chunk（dense_score is None）放行，词面命中保留为另一类弱信号。
        if score_threshold is not None and results:
            results = [
                r for r in results
                if r.dense_score is None or r.dense_score >= score_threshold
            ]

        # 5. Increment hit_count + emit governance events (Plan 32 M1.3).
        #    Uses a short dedicated session so retrieval path doesn't couple to caller's tx.
        #    hit_count is a rollup counter (kept for fast queries); the canonical
        #    record is in chunk_usage_events (event_type=hit) for time-window aggregation.
        # M6.5 — is_test=True 跳过：测试性 query 不算"真实使用"，否则会污染
        # 覆盖度 / 可用性 / 知识盲区告警等治理画像。
        if is_test:
            pass
        elif results:
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
        # Plan 35 — 记录每次检索（按 query_type）做 auto-tuning 数据底座。
        # Workbench M1.3 — params_json / latency_ms / created_by 让 UI 能
        # 完整重放并按用户筛选。
        try:
            from app.knowledge.retrieval.query_classifier import classify
            from app.knowledge.retrieval.models import RetrievalLog
            qtype = classify(query_used).type
            params_snapshot = {
                "top_k": top_k,
                "folder_ids": folder_ids or [],
                "rewrite": rewrite,
                "bm25_weight": bm25_weight,
                "vector_weight": vector_weight,
                "score_threshold": score_threshold,
                "rerank_enabled": bool(reranker_provider_id and reranker_model_name),
                "reranker_model": reranker_model_name,
                "embedding_registry_id": (
                    str(embedding_model_registry_id) if embedding_model_registry_id else None
                ),
                "embedding_provider_id": (
                    str(embedding_provider_id) if embedding_provider_id else None
                ),
                "embedding_model_name": embedding_model_name,
            }
            # Workbench M2.1 — snapshot hit list. Trim content to 500 chars
            # so JSONB stays compact even with top_k=20+. Keeping per-stage
            # scores so history replay shows the same breakdown bar.
            results_snapshot = [
                {
                    "chunk_id": r.chunk_id,
                    "content": (r.content or "")[:500],
                    "score": r.score,
                    "dense_score": r.dense_score,
                    "bm25_score": r.bm25_score,
                    "rerank_score": r.rerank_score,
                    "document_id": r.document_id,
                    "folder_id": r.folder_id,
                    "level": r.level,
                    "title": r.title,
                    "metadata": r.metadata or {},
                    "source_kb_id": r.source_kb_id,
                }
                for r in results
            ]
            async with async_session() as log_db:
                for kid in kb_ids:
                    log_db.add(RetrievalLog(
                        kb_id=uuid.UUID(str(kid)),
                        query=query_used[:500],
                        query_type=qtype,
                        top_k=top_k,
                        result_count=len(results),
                        params_json=params_snapshot,
                        latency_ms=elapsed,
                        created_by=created_by,
                        results_json=results_snapshot,
                        is_test=is_test,
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

    async def retrieve_agentic(
        self,
        query: str,
        kb_ids: list[str],
        *,
        top_k: int = 10,
        per_subquery_k: int = 6,
        **retrieve_kwargs,
    ) -> RetrievalResult:
        """Plan 37 — Agentic RAG: LLM 规划是否拆分子查询；命中 decompose 时
        每条 sub-query 独立检索，再用 fusion 合并。规划失败/单 query 时
        透传到 ``retrieve``。

        ``retrieve_kwargs`` 透传给底层 ``retrieve``（embedding/rewrite/rerank
        等参数），但 ``top_k`` 在子查询阶段被替换为 ``per_subquery_k``。
        """
        from app.knowledge.retrieval.agentic_planner import (
            build_default_chat_fn, plan,
        )
        from app.knowledge.retrieval.fusion import fuse_results

        chat_fn = build_default_chat_fn()
        try:
            agentic_plan = await plan(query, chat_fn=chat_fn)
        except Exception:
            logger.debug("agentic_plan_failed", exc_info=True)
            return await self.retrieve(query=query, kb_ids=kb_ids, top_k=top_k, **retrieve_kwargs)

        if agentic_plan.strategy != "decompose" or len(agentic_plan.subqueries) < 2:
            return await self.retrieve(query=query, kb_ids=kb_ids, top_k=top_k, **retrieve_kwargs)

        # 并发跑每条 sub-query
        import asyncio as _asyncio
        sub_results: list[RetrievalResult] = await _asyncio.gather(
            *[
                self.retrieve(query=sub, kb_ids=kb_ids, top_k=per_subquery_k, **retrieve_kwargs)
                for sub in agentic_plan.subqueries
            ],
            return_exceptions=False,
        )
        # 合并所有结果，按 chunk_id 去重，然后跑 fuse_results 做多样性排序
        seen: dict[str, SearchResult] = {}
        for sr in sub_results:
            for r in sr.results:
                if not r.chunk_id:
                    continue
                if r.chunk_id not in seen or r.score > seen[r.chunk_id].score:
                    seen[r.chunk_id] = r
        merged = list(seen.values())
        merged.sort(key=lambda r: r.score, reverse=True)
        fused = fuse_results(merged, top_k=top_k)

        total_searched = sum(s.total_searched for s in sub_results)
        timing = sum(s.timing_ms for s in sub_results)
        logger.info(
            "agentic_decomposed_retrieval",
            original=query, subs=agentic_plan.subqueries,
            reason=agentic_plan.reason, candidates=len(merged),
            final=len(fused),
        )
        return RetrievalResult(
            results=fused,
            query_used=" | ".join(agentic_plan.subqueries),
            timing_ms=timing,
            total_searched=total_searched,
        )

    async def _filter_invisible(self, results: list[SearchResult]) -> list[SearchResult]:
        """聚合不可见过滤：
        - 归档文档（Plan 32 M3）：仍走 documents.is_archived 检查
        - 审核期内容隔离（Plan 39）：走 chunks.review_excluded 派生列，
          替代原 JOIN documents.review_status 实现，性能更好且统一接入
          多 source_type（条目型 KB 同样用 chunks.review_excluded）

        失败时保守通过，不让治理故障阻断检索。"""
        chunk_ids: set[uuid.UUID] = set()
        doc_ids: set[uuid.UUID] = set()
        for r in results:
            if r.chunk_id:
                try:
                    chunk_ids.add(uuid.UUID(r.chunk_id))
                except Exception:
                    pass
            if r.document_id:
                try:
                    doc_ids.add(uuid.UUID(r.document_id))
                except Exception:
                    pass
        if not chunk_ids and not doc_ids:
            return results
        try:
            from sqlalchemy import select as _select
            from app.knowledge.models import Chunk, Document
            invisible_chunks: set[str] = set()
            invisible_docs: set[str] = set()
            async with async_session() as db:
                # 1. Plan 39 — chunks.review_excluded 派生列（pending / rejected）
                if chunk_ids:
                    excluded_rows = (await db.execute(
                        _select(Chunk.id).where(
                            Chunk.id.in_(chunk_ids),
                            Chunk.review_excluded.is_(True),
                        )
                    )).scalars().all()
                    invisible_chunks = {str(cid) for cid in excluded_rows}
                # 2. Plan 32 M3 — documents.is_archived
                if doc_ids:
                    archived_rows = (await db.execute(
                        _select(Document.id).where(
                            Document.id.in_(doc_ids),
                            Document.is_archived.is_(True),
                        )
                    )).scalars().all()
                    invisible_docs = {str(did) for did in archived_rows}
            if invisible_chunks or invisible_docs:
                filtered = [
                    r for r in results
                    if r.chunk_id not in invisible_chunks
                    and r.document_id not in invisible_docs
                ]
                logger.debug(
                    "retrieval_invisible_filtered",
                    dropped=len(results) - len(filtered),
                    by_review=len(invisible_chunks),
                    by_archive=len(invisible_docs),
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
