"""Redundancy pair core algorithm (Plan 26 M1).

给定向量矩阵与 ids，找出余弦相似度 >= threshold 的 (i, j) 对 (i < j)。
使用归一化向量 + 矩阵乘法，一次性得到相似度矩阵；对大量 chunk 分批。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class RedundancyPair:
    a_id: str
    b_id: str
    similarity: float


DEFAULT_THRESHOLD = 0.92


def _normalize_rows(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def find_redundant_pairs(
    ids: list[str],
    vectors: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
    block_size: int = 256,
) -> list[RedundancyPair]:
    """返回 similarity >= threshold 的所有 (i < j) 对，按相似度降序。

    ``vectors`` shape (n, dim)。数组式分块乘法避免 n^2 同时开显存：
    对大 n（>1w）也能在 O(block*n) 显存内完成。
    """
    if vectors.ndim != 2 or vectors.shape[0] != len(ids):
        raise ValueError("vectors shape mismatch ids length")
    if len(ids) < 2:
        return []

    normed = _normalize_rows(vectors.astype(np.float32))
    n = len(ids)
    pairs: list[RedundancyPair] = []
    for i0 in range(0, n, block_size):
        i1 = min(i0 + block_size, n)
        block = normed[i0:i1]
        sims = block @ normed.T  # (block, n)
        for row_off, i in enumerate(range(i0, i1)):
            # 只看 j > i 的上三角，避免重复对
            js = np.where(sims[row_off, i + 1:] >= threshold)[0] + (i + 1)
            for j in js:
                pairs.append(RedundancyPair(
                    a_id=ids[i], b_id=ids[j],
                    similarity=float(sims[row_off, j]),
                ))
    pairs.sort(key=lambda p: p.similarity, reverse=True)
    return pairs
