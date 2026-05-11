"""HybridSearcher score-breakdown tests (Workbench M1.2).

Mocks Milvus client to verify:
- two single-route searches are issued (not one hybrid_search)
- per-route raw scores propagate to SearchResult.dense_score / bm25_score
- weighted RRF fusion gives the expected ranking
- weight=0 disables a route's contribution to ranking but keeps its raw score
- chunks matching only one route still appear with the other score=None
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.knowledge.retrieval.searcher import HybridSearcher, _RRF_K


def _hit(chunk_id: str, distance: float, **entity_overrides):
    """Mimic the dict shape pymilvus returns from `client.search`."""
    base_entity = {
        "content": f"content {chunk_id}",
        "document_id": "doc1",
        "folder_id": None,
        "level": 0,
        "title": "t",
        "metadata_json": "",
    }
    base_entity.update(entity_overrides)
    return {"id": chunk_id, "distance": distance, "entity": base_entity}


def _make_searcher(dense_hits, sparse_hits):
    """Wire a HybridSearcher whose Milvus client returns the supplied hits.

    The actual `_client.search` is called twice per `search()` call (dense
    + bm25); use side_effect to return them in order, each wrapped in the
    outer list shape pymilvus returns.
    """
    fake_client = MagicMock()
    fake_client.search.side_effect = [[dense_hits], [sparse_hits]]

    fake_milvus = MagicMock()
    fake_milvus.collection_exists.return_value = True
    fake_milvus._client = fake_client
    return HybridSearcher(milvus=fake_milvus), fake_client


def test_search_issues_two_single_route_calls():
    """Verify the rewrite from hybrid_search() to two search() calls."""
    s, client = _make_searcher(
        dense_hits=[_hit("a", 0.9)],
        sparse_hits=[_hit("a", 0.8)],
    )
    s.search("kb_x", [0.1, 0.2], "query text", top_k=5)
    assert client.search.call_count == 2
    # First call dense, second call bm25 — anns_field tells us which
    fields = [c.kwargs.get("anns_field") for c in client.search.call_args_list]
    assert fields == ["dense_vector", "sparse_vector"]


def test_per_route_scores_attached_when_both_routes_match():
    s, _ = _make_searcher(
        dense_hits=[_hit("a", 0.91), _hit("b", 0.42)],
        sparse_hits=[_hit("a", 0.65), _hit("b", 0.31)],
    )
    out = s.search("kb_x", [0.1], "q", top_k=5)
    by_id = {r.chunk_id: r for r in out}
    assert by_id["a"].dense_score == 0.91
    assert by_id["a"].bm25_score == 0.65
    assert by_id["b"].dense_score == 0.42
    assert by_id["b"].bm25_score == 0.31
    # rerank didn't run
    assert all(r.rerank_score is None for r in out)


def test_chunk_matching_only_one_route_has_other_score_none():
    """Dense found 'a', BM25 found 'b' — each route exclusively, no overlap."""
    s, _ = _make_searcher(
        dense_hits=[_hit("a", 0.9)],
        sparse_hits=[_hit("b", 0.7)],
    )
    out = s.search("kb_x", [0.1], "q", top_k=5)
    by_id = {r.chunk_id: r for r in out}
    assert by_id["a"].dense_score == 0.9
    assert by_id["a"].bm25_score is None
    assert by_id["b"].dense_score is None
    assert by_id["b"].bm25_score == 0.7


def test_rrf_fusion_ranks_dual_route_match_above_single_route():
    """A chunk that hits both routes at rank 0 should beat one that hits
    only one route at rank 0 — that's the whole point of RRF."""
    s, _ = _make_searcher(
        dense_hits=[_hit("both", 0.5), _hit("dense_only", 0.8)],
        sparse_hits=[_hit("both", 0.5), _hit("bm25_only", 0.8)],
    )
    out = s.search("kb_x", [0.1], "q", top_k=5)
    # 'both' should rank first regardless of raw score being lower
    assert out[0].chunk_id == "both"


def test_weight_zero_disables_route_in_ranking_but_keeps_raw_score():
    """Setting bm25_weight=0 should make BM25 not contribute to score, but
    a chunk that matched BM25 still has bm25_score recorded for diagnosis.
    """
    s, _ = _make_searcher(
        dense_hits=[_hit("low_dense", 0.3)],
        sparse_hits=[_hit("high_bm25", 0.9)],
    )
    out = s.search(
        "kb_x", [0.1], "q", top_k=5,
        bm25_weight=0.0, vector_weight=1.0,
    )
    by_id = {r.chunk_id: r for r in out}
    # Dense-only 'low_dense' should now outrank BM25-only 'high_bm25' since
    # BM25 contributes 0 to fused score.
    assert out[0].chunk_id == "low_dense"
    # But BM25 raw score still preserved on 'high_bm25' for the UI
    assert by_id["high_bm25"].bm25_score == 0.9


def test_collection_not_exists_returns_empty_without_calling_search():
    fake_milvus = MagicMock()
    fake_milvus.collection_exists.return_value = False
    s = HybridSearcher(milvus=fake_milvus)
    out = s.search("kb_missing", [0.1], "q", top_k=5)
    assert out == []
    fake_milvus._client.search.assert_not_called()


def test_rrf_constant_is_60():
    """Workbench score breakdown contract: K=60 stays put. Changing it
    silently changes ranking semantics across the whole product."""
    assert _RRF_K == 60
