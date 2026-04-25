"""Multi-Source Retrieval Fusion (Plan 36 M1).

Spec phasing §Retrieval Enhancement: "Multi-Source retrieval
(cross-KB with intelligent fusion)"。

把跨 KB 候选的"原始按分排序"替换成三步流水线：

  1. **Source weighting** —— 每个 KB 自带一个 0..1 的权重（默认从治理
     `health_score` 派生：(score-50)/50 截断到 [0.5, 1.5]）。命中分
     score' = score * weight_kb，弱 KB 的"水货"被自然降权。

  2. **Cross-KB dedup** —— 给定 ChunkCrossKBRedundancyPair 的列表，
     若两个候选互为冗余对，保留 source_weight 高 + score 高的那一条。

  3. **MMR diversity** —— Maximal Marginal Relevance:
        pick = argmax( λ * relevance - (1-λ) * max_sim_to_picked )
     近似实现：用 chunk content 的 token 集合 Jaccard 替代向量相似度
     （避免重新调 embedding；纯函数即可）。

所有阶段纯函数，无 DB / Milvus 依赖；调用方传齐数据即可单测。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.knowledge.retrieval.searcher import SearchResult


DEFAULT_LAMBDA = 0.7  # MMR 平衡：偏向相关性


@dataclass
class FusionConfig:
    """允许调用方覆盖默认参数。"""
    enable_source_weighting: bool = True
    enable_cross_kb_dedup: bool = True
    enable_mmr: bool = True
    mmr_lambda: float = DEFAULT_LAMBDA


def health_to_weight(health_score: float | None) -> float:
    """0..100 健康分 → 0.5..1.5 检索权重。
    50 分 = 1.0；80+ = 1.5；20- = 0.5。空值给 1.0（中性）。"""
    if health_score is None:
        return 1.0
    return max(0.5, min(1.5, 0.5 + health_score / 100.0))


def _content_tokens(text: str) -> set[str]:
    if not text:
        return set()
    # 简单 ASCII + 中文双字符滑窗，兼顾中英
    out: set[str] = set()
    s = text.lower()
    # ASCII 词
    cur = []
    for ch in s:
        if ch.isalnum() and ord(ch) < 128:
            cur.append(ch)
        else:
            if cur:
                out.add("".join(cur))
                cur = []
            if "\u4e00" <= ch <= "\u9fff":
                out.add(ch)  # 单字
    if cur:
        out.add("".join(cur))
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def fuse_results(
    results: list[SearchResult],
    *,
    source_weights: dict[str, float] | None = None,
    dedup_pairs: list[tuple[str, str]] | None = None,
    top_k: int = 10,
    config: FusionConfig | None = None,
) -> list[SearchResult]:
    """三步融合。返回最多 top_k 条结果，按融合后顺序排列。

    ``source_weights``: kb_id → 0.5..1.5 倍率
    ``dedup_pairs``:   list of (chunk_a_id, chunk_b_id)，由 Plan 31 cross-KB
                       redundancy 表预计算
    """
    cfg = config or FusionConfig()
    if not results:
        return []

    # 1) source weighting
    if cfg.enable_source_weighting and source_weights:
        for r in results:
            w = source_weights.get(str(r.source_kb_id) if r.source_kb_id else "", 1.0)
            r.score = float(r.score) * float(w)
        results.sort(key=lambda r: r.score, reverse=True)

    # 2) cross-KB dedup
    if cfg.enable_cross_kb_dedup and dedup_pairs:
        kept_ids: set[str] = set()
        # 把对转 dict 方便双向查
        pair_set = {tuple(sorted(p)) for p in dedup_pairs}
        ordered: list[SearchResult] = []
        # 按 score 降序遍历；遇到同对的另一边时跳过
        for r in results:
            cid = str(r.chunk_id)
            duplicate = False
            for existing in ordered:
                pair = tuple(sorted([cid, str(existing.chunk_id)]))
                if pair in pair_set:
                    duplicate = True
                    break
            if not duplicate:
                ordered.append(r)
                kept_ids.add(cid)
        results = ordered

    # 3) MMR diversity
    if cfg.enable_mmr and len(results) > 1:
        # 缓存每条 token set
        token_cache = {r.chunk_id: _content_tokens(r.content) for r in results}
        scores = {r.chunk_id: float(r.score) for r in results}
        max_score = max(scores.values()) or 1.0

        picked: list[SearchResult] = []
        candidates = list(results)
        # 先拿最高分作为种子
        candidates.sort(key=lambda r: scores[r.chunk_id], reverse=True)
        picked.append(candidates.pop(0))

        while candidates and len(picked) < top_k:
            best_idx = 0
            best_mmr = -1e9
            for i, c in enumerate(candidates):
                rel = scores[c.chunk_id] / max_score
                # max similarity 与已选项
                a = token_cache[c.chunk_id]
                max_sim = 0.0
                for p in picked:
                    sim = _jaccard(a, token_cache[p.chunk_id])
                    if sim > max_sim:
                        max_sim = sim
                mmr = cfg.mmr_lambda * rel - (1 - cfg.mmr_lambda) * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = i
            picked.append(candidates.pop(best_idx))
        results = picked

    return results[:top_k]
