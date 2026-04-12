from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import structlog
from pymilvus import AnnSearchRequest, RRFRanker

from app.knowledge.milvus.service import MilvusService

logger = structlog.get_logger(__name__)


@dataclass
class SearchResult:
    chunk_id: str
    content: str
    score: float
    document_id: str
    folder_id: str | None
    level: int
    title: str
    metadata: dict = field(default_factory=dict)
    source_kb_id: str | None = None


def _normalize_scores(results: list[SearchResult]) -> list[SearchResult]:
    if not results:
        return results
    max_score = max(r.score for r in results)
    if max_score <= 0:
        return results
    for r in results:
        r.score = r.score / max_score
    return results


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
    ) -> list[SearchResult]:
        filter_expr = ""
        if folder_ids:
            ids_str = ", ".join(f'"{fid}"' for fid in folder_ids)
            filter_expr = f"folder_id in [{ids_str}]"

        dense_req = AnnSearchRequest(
            data=[query_vector],
            anns_field="dense_vector",
            param={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=top_k,
            expr=filter_expr or None,
        )
        sparse_req = AnnSearchRequest(
            data=[query_text],
            anns_field="sparse_vector",
            param={"metric_type": "BM25"},
            limit=top_k,
            expr=filter_expr or None,
        )

        raw = self._milvus._client.hybrid_search(
            collection_name=collection_name,
            reqs=[dense_req, sparse_req],
            ranker=RRFRanker(k=60),
            limit=top_k,
            output_fields=[
                "content", "document_id", "folder_id",
                "level", "title", "metadata_json",
            ],
        )

        results: list[SearchResult] = []
        for hit in raw[0]:
            entity = hit.entity
            meta = {}
            raw_meta = entity.get("metadata_json", "")
            if raw_meta:
                try:
                    meta = json.loads(raw_meta)
                except (json.JSONDecodeError, TypeError):
                    pass

            results.append(SearchResult(
                chunk_id=hit.id,
                content=entity.get("content", ""),
                score=hit.distance,
                document_id=entity.get("document_id", ""),
                folder_id=entity.get("folder_id"),
                level=entity.get("level", 0),
                title=entity.get("title", ""),
                metadata=meta,
            ))
        return results

    async def multi_kb_search(
        self,
        kb_configs: list[dict],
        query_vector: list[float],
        query_text: str,
        top_k: int = 10,
        folder_ids: list[str] | None = None,
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

        merged = _normalize_scores(merged)
        merged.sort(key=lambda r: r.score, reverse=True)
        return merged[:top_k]
