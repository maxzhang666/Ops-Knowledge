"""Cross-KB redundancy core algorithm (Plan 31 M2).

跨库相似度比较（每个 KB 取代表性样本）:
  vectors_a (Na, dim), vectors_b (Nb, dim) → 找 sim ≥ threshold 的对。

使用归一化 + 矩阵乘法分块（避免 Na*Nb 同时占内存），与同库版本类似。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


CROSS_DEFAULT_THRESHOLD = 0.85
CROSS_DEFAULT_MAX_PAIRS_PER_KB_PAIR = 100


@dataclass
class CrossKBPair:
    a_id: str
    b_id: str
    similarity: float


def _normalize_rows(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def find_cross_kb_pairs(
    ids_a: list[str],
    vectors_a: np.ndarray,
    ids_b: list[str],
    vectors_b: np.ndarray,
    threshold: float = CROSS_DEFAULT_THRESHOLD,
    max_pairs: int = CROSS_DEFAULT_MAX_PAIRS_PER_KB_PAIR,
    block_size: int = 256,
) -> list[CrossKBPair]:
    """返回 sim ≥ threshold 的 (a_id, b_id) 对，按相似度降序，截断到 max_pairs。"""
    if vectors_a.ndim != 2 or vectors_b.ndim != 2:
        raise ValueError("vectors must be 2D")
    if vectors_a.shape[0] != len(ids_a) or vectors_b.shape[0] != len(ids_b):
        raise ValueError("ids/vectors length mismatch")
    if not ids_a or not ids_b:
        return []

    a = _normalize_rows(vectors_a.astype(np.float32))
    b = _normalize_rows(vectors_b.astype(np.float32))
    pairs: list[CrossKBPair] = []
    for i0 in range(0, len(ids_a), block_size):
        i1 = min(i0 + block_size, len(ids_a))
        block = a[i0:i1]
        sims = block @ b.T  # (block, Nb)
        for row_off, i in enumerate(range(i0, i1)):
            js = np.where(sims[row_off] >= threshold)[0]
            for j in js:
                pairs.append(CrossKBPair(
                    a_id=ids_a[i], b_id=ids_b[int(j)],
                    similarity=float(sims[row_off, int(j)]),
                ))
    pairs.sort(key=lambda p: p.similarity, reverse=True)
    return pairs[:max_pairs]
