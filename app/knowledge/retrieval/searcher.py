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
    "level", "title", "metadata_json", "chunk_tags",
]

# Spec 25 §5.3 — L4 rerank: query 与 canonical embedding 取 top-K 作为
# "本次 query 的语义相关 tag 集合"，与 chunk_tags 求交集贡献 boost。
_DEFAULT_TOP_K_CANONICALS = 5


def _cosine_sim(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _select_relevant_canonicals(
    query_vector: list[float],
    canonical_embeddings: dict[str, list[float]],
    top_k: int = _DEFAULT_TOP_K_CANONICALS,
) -> set[str]:
    """对 query 与每个 canonical 算 cosine，取 top-K（且相似度 > 0）。"""
    if not canonical_embeddings or not query_vector:
        return set()
    scored = [
        (canon, _cosine_sim(query_vector, vec))
        for canon, vec in canonical_embeddings.items()
    ]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return {c for c, s in scored[:top_k] if s > 0}


def _apply_tag_boost(
    merged: dict[str, dict],
    query_vector: list[float],
    canonical_embeddings: dict[str, list[float]] | None,
    boost_weight: float,
) -> None:
    """在 RRF 融合 score 之上叠加 tag boost；in-place 修改 row['fused']。

    boost = hit_count * boost_weight，hit_count = chunk_tags ∩ top-K canonicals。
    无 canonical embeddings / boost_weight<=0 时 noop（feature flag）。
    """
    if not canonical_embeddings or boost_weight <= 0:
        return
    relevant = _select_relevant_canonicals(query_vector, canonical_embeddings)
    if not relevant:
        return
    for row in merged.values():
        entity = row.get("entity") or {}
        chunk_tags = entity.get("chunk_tags") or []
        if not isinstance(chunk_tags, (list, tuple)):
            continue
        hit_count = sum(1 for t in chunk_tags if t in relevant)
        if hit_count <= 0:
            continue
        row["fused"] = float(row.get("fused", 0.0)) + hit_count * boost_weight
        row["tag_boost"] = hit_count * boost_weight


def _build_tag_filter_expr(tag_filter: dict | None) -> str | None:
    """Spec 25 L2 — 把 {any_of, all_of, not} 翻译成 milvus filter 表达式。

    any_of: chunk_tags ∩ given ≠ ∅ → array_contains_any(chunk_tags, [...])
    all_of: chunk_tags ⊇ given → array_contains_all(chunk_tags, [...])
    not:    chunk_tags ∩ given = ∅ → NOT array_contains_any(chunk_tags, [...])

    三种语义可任意组合（AND 串联）。空 dict / 无字段返回 None。
    """
    if not tag_filter or not isinstance(tag_filter, dict):
        return None

    def _quote_list(xs: list[str]) -> str:
        return "[" + ", ".join(f'"{x}"' for x in xs if x) + "]"

    parts: list[str] = []
    any_of = tag_filter.get("any_of") or []
    all_of = tag_filter.get("all_of") or []
    not_in = tag_filter.get("not") or []
    if any_of:
        parts.append(f"array_contains_any(chunk_tags, {_quote_list(any_of)})")
    if all_of:
        parts.append(f"array_contains_all(chunk_tags, {_quote_list(all_of)})")
    if not_in:
        parts.append(f"not array_contains_any(chunk_tags, {_quote_list(not_in)})")
    if not parts:
        return None
    return " and ".join(parts)


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
        tag_filter: dict | None = None,
        # Spec 25 L4 — query 与 KB canonical embeddings 算语义相关
        # tag boost；retrieval service 端按 KB tag_settings 决定是否注入。
        tag_boost_weight: float = 0.0,
        canonical_embeddings: dict[str, list[float]] | None = None,
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

        parts: list[str] = []
        if folder_ids:
            ids_str = ", ".join(f'"{fid}"' for fid in folder_ids)
            parts.append(f"folder_id in [{ids_str}]")
        tag_expr = _build_tag_filter_expr(tag_filter)
        if tag_expr:
            parts.append(tag_expr)
        filter_expr = " and ".join(parts) if parts else None

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

        # Spec 25 L4 — tag boost：query 与 canonical embedding 取 top-K 相关
        # canonicals，命中 chunk_tags 的 chunk 在 fused 之上加权
        _apply_tag_boost(merged, query_vector, canonical_embeddings, tag_boost_weight)

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
        tag_filter: dict | None = None,
        tag_boost_weight: float = 0.0,
        canonical_embeddings_by_kb: dict[str, dict[str, list[float]]] | None = None,
    ) -> list[SearchResult]:
        async def _search_one(cfg: dict) -> list[SearchResult]:
            loop = asyncio.get_event_loop()
            # 每 KB 自己的 canonical embeddings（不同 KB 字典不同）
            kb_canon = (
                (canonical_embeddings_by_kb or {}).get(cfg.get("kb_id") or "")
                if canonical_embeddings_by_kb else None
            )
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
                    tag_filter,
                    tag_boost_weight,
                    kb_canon,
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
