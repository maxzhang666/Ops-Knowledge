from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import structlog

from app.knowledge.milvus.service import MilvusService

logger = structlog.get_logger(__name__)

# RRF k constant (Reciprocal Rank Fusion). Larger k flattens the curve;
# 60 is the standard from the original RRF paper and matches what
# pymilvus.RRFRanker(k=60) was using server-side before this rewrite.
_RRF_K = 60


@dataclass
class SearchResult:
    chunk_id: str
    content: str
    # `score` is the final score the caller ranks on. Equal to rerank_score
    # if rerank ran, else the RRF-fused score.
    score: float
    document_id: str
    folder_id: str | None
    level: int
    title: str
    metadata: dict = field(default_factory=dict)
    source_kb_id: str | None = None
    # Per-stage score breakdown for the Retrieval Workbench. None when the
    # stage didn't run for this row (e.g. matched only via dense → bm25_score
    # is None; rerank disabled → rerank_score is None).
    dense_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None


def _normalize_scores(results: list[SearchResult]) -> list[SearchResult]:
    """Min-max normalize fused scores to [0,1].

    M6.2 起不再被 `multi_kb_search` 调用 —— 归一化把"排第一"伪装成"相关度=1.0"
    误导用户。保留函数仅为向后兼容潜在外部调用，新代码请直接读 `score`
    （RRF 融合分，用于排序）和 `dense_score`（cosine，用于判定相关度）。
    """
    if not results:
        return results
    min_score = min(r.score for r in results)
    max_score = max(r.score for r in results)
    score_range = max_score - min_score
    if score_range <= 0:
        for r in results:
            r.score = 1.0
        return results
    for r in results:
        r.score = (r.score - min_score) / score_range
    return results


def _parse_meta(raw_meta: object) -> dict:
    if not raw_meta:
        return {}
    try:
        return json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta)
    except (json.JSONDecodeError, TypeError):
        return {}


_OUTPUT_FIELDS = [
    "content", "document_id", "folder_id",
    "level", "title", "metadata_json",
]


class HybridSearcher:
    def __init__(self, milvus: MilvusService | None = None):
        self._milvus = milvus or MilvusService()

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        query_text: str,
        top_k: int = 10,
        folder_ids: list[str] | None = None,
        bm25_weight: float = 1.0,
        vector_weight: float = 1.0,
    ) -> list[SearchResult]:
        """Hybrid retrieval with per-route score breakdown.

        Runs dense and BM25 searches separately so every result carries
        ``dense_score`` / ``bm25_score`` (None when only one route hit).
        Final ``score`` = RRF fusion with weighted ranks
        ``vector_weight * 1/(K + dense_rank) + bm25_weight * 1/(K + bm25_rank)``.
        Setting one weight to 0 effectively disables that route in the
        ranking but the per-route raw scores are still returned for diagnosis.
        """
        # Pre-check: a KB that's never had a document processed has no Milvus
        # collection yet. Hitting search would raise "collection not found"
        # (code 100). Treat as a valid "no index yet" state.
        if not self._milvus.collection_exists(collection_name):
            logger.debug("collection_not_yet_created", collection=collection_name)
            return []

        filter_expr = None
        if folder_ids:
            ids_str = ", ".join(f'"{fid}"' for fid in folder_ids)
            filter_expr = f"folder_id in [{ids_str}]"

        # Each route over-fetches a bit so RRF has reasonable rank coverage
        # for items that match strongly on only one route.
        per_route_k = max(top_k * 2, 20)
        dense_hits = self._milvus._client.search(
            collection_name=collection_name,
            data=[query_vector],
            anns_field="dense_vector",
            search_params={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=per_route_k,
            filter=filter_expr,
            output_fields=_OUTPUT_FIELDS,
        )[0]
        bm25_hits = self._milvus._client.search(
            collection_name=collection_name,
            data=[query_text],
            anns_field="sparse_vector",
            search_params={"metric_type": "BM25"},
            limit=per_route_k,
            filter=filter_expr,
            output_fields=_OUTPUT_FIELDS,
        )[0]

        # Aggregate by chunk_id, recording per-route raw score + rank.
        merged: dict[str, dict] = {}
        for rank, hit in enumerate(dense_hits):
            cid = hit["id"]
            row = merged.setdefault(cid, {"entity": hit.get("entity") or {}})
            row["dense_score"] = float(hit.get("distance", 0.0))
            row["dense_rank"] = rank
        for rank, hit in enumerate(bm25_hits):
            cid = hit["id"]
            row = merged.setdefault(cid, {"entity": hit.get("entity") or {}})
            # BM25 hits without a corresponding dense entity must still seed
            # the entity dict so downstream rendering has fields.
            if not row.get("entity"):
                row["entity"] = hit.get("entity") or {}
            row["bm25_score"] = float(hit.get("distance", 0.0))
            row["bm25_rank"] = rank

        # RRF fusion. Weights scale each route's contribution.
        for row in merged.values():
            d_rank = row.get("dense_rank")
            s_rank = row.get("bm25_rank")
            score = 0.0
            if d_rank is not None:
                score += vector_weight * (1.0 / (_RRF_K + d_rank + 1))
            if s_rank is not None:
                score += bm25_weight * (1.0 / (_RRF_K + s_rank + 1))
            row["fused"] = score

        ranked = sorted(merged.items(), key=lambda kv: kv[1]["fused"], reverse=True)[:top_k]

        results: list[SearchResult] = []
        for cid, row in ranked:
            entity = row.get("entity") or {}
            results.append(SearchResult(
                chunk_id=str(cid),
                content=entity.get("content", ""),
                score=row["fused"],
                document_id=entity.get("document_id", ""),
                folder_id=entity.get("folder_id"),
                level=entity.get("level", 0),
                title=entity.get("title", ""),
                metadata=_parse_meta(entity.get("metadata_json", "")),
                dense_score=row.get("dense_score"),
                bm25_score=row.get("bm25_score"),
            ))
        return results

    async def multi_kb_search(
        self,
        kb_configs: list[dict],
        query_vector: list[float],
        query_text: str,
        top_k: int = 10,
        folder_ids: list[str] | None = None,
        bm25_weight: float = 1.0,
        vector_weight: float = 1.0,
    ) -> list[SearchResult]:
        async def _search_one(cfg: dict) -> list[SearchResult]:
            loop = asyncio.get_event_loop()
            hits = await loop.run_in_executor(
                None,
                lambda: self.search(
                    cfg["collection_name"],
                    query_vector,
                    query_text,
                    top_k,
                    folder_ids,
                    bm25_weight,
                    vector_weight,
                ),
            )
            for h in hits:
                h.source_kb_id = cfg.get("kb_id")
            return hits

        tasks = [_search_one(cfg) for cfg in kb_configs]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: list[SearchResult] = []
        for batch in all_results:
            if isinstance(batch, Exception):
                logger.warning("kb_search_failed", error=str(batch))
                continue
            merged.extend(batch)

        # M6.2 — 不再 min-max normalize。RRF 融合分本身跨 KB 可比（同 K 同公式），
        # 归一化反而把"排第一"伪装成"相关度=1.0"误导用户。绝对相关度走 dense_score。
        merged.sort(key=lambda r: r.score, reverse=True)
        return merged[:top_k]
