"""RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval) 核心算法 (P24.M4).

给定 L0 叶子 chunk 及其 embedding：
  1. 用 k-means 聚类（numpy 纯实现，避免引入 sklearn 依赖）
  2. 对每个 ``cluster size >= 2`` 的簇用 LLM 生成摘要 → 形成 L1 chunk
  3. 对 L1 簇摘要再 embed、聚类、摘要 → L2...
  4. 直到簇数 <=1 或达到 ``max_levels``

生成的 L≥1 chunk 与 L0 共享同一 KB / Milvus collection，检索时自然
被 hybrid_search 召回；摘要节点通过 ``metadata.raptor_children`` 指向
源 chunk id 列表，方便调试与 UI 追溯。

注意这个模块不接触 DB / Milvus —— 纯算法 + 函数接口，方便单元测试。
集成由 ``raptor_task.py`` 负责。
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RaptorSeed:
    """聚类输入：已有 chunk id + content + embedding 的节点。"""
    id: uuid.UUID
    content: str
    embedding: np.ndarray  # shape (dim,)


@dataclass
class RaptorSummary:
    """一层聚类的摘要结果：新节点 id + 简介 + 本级成员 chunk id 列表 + level。"""
    id: uuid.UUID
    summary: str
    member_ids: list[uuid.UUID]
    level: int
    # 下一轮聚类要用 —— 调用方 embed 填进来
    embedding: np.ndarray | None = field(default=None)


# ─── k-means (numpy) ────────────────────────────────────────────────

def _kmeans(
    vectors: np.ndarray, k: int, *,
    max_iter: int = 30, seed: int = 0,
) -> np.ndarray:
    """简化版 Lloyd k-means。返回 shape (n,) 的 cluster labels [0, k)。

    * 纯 numpy，避免 sklearn 依赖
    * 对 RAPTOR 场景足够：chunk 数量通常 <= 几千，欧氏距离 ok
    * 空簇再 seed 为远离 centroid 的随机点，避免永久空簇
    """
    n, _dim = vectors.shape
    if k >= n:
        return np.arange(n)
    rng = np.random.default_rng(seed)
    # k-means++ 初始化：首个随机，后续按距离加权
    init_idx = [int(rng.integers(n))]
    for _ in range(1, k):
        d2 = np.min(
            np.linalg.norm(vectors[:, None, :] - vectors[init_idx][None, :, :], axis=2) ** 2,
            axis=1,
        )
        if d2.sum() <= 0:
            init_idx.append(int(rng.integers(n)))
        else:
            probs = d2 / d2.sum()
            init_idx.append(int(rng.choice(n, p=probs)))
    centers = vectors[init_idx].copy()

    labels = np.zeros(n, dtype=int)
    for _ in range(max_iter):
        dists = np.linalg.norm(vectors[:, None, :] - centers[None, :, :], axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for i in range(k):
            mask = labels == i
            if mask.any():
                centers[i] = vectors[mask].mean(axis=0)
            else:
                centers[i] = vectors[int(rng.integers(n))]
    return labels


def _pick_k(n_samples: int) -> int:
    """启发式：簇数 ≈ sqrt(n/2)，范围 [2, 20]。小样本直接 1 簇 (跳过聚类)。"""
    if n_samples < 4:
        return 1
    k = max(2, int(np.sqrt(n_samples / 2)))
    return min(k, 20)


# ─── 核心构建流程 ───────────────────────────────────────────────────

async def build_raptor_levels(
    seeds: list[RaptorSeed],
    *,
    summarize_fn,                         # async ([str]) -> str
    embed_fn,                             # async ([str]) -> list[list[float]]
    max_levels: int = 3,
    min_cluster_size: int = 2,
) -> list[RaptorSummary]:
    """递归聚类 + 摘要，返回所有层级的 summary 节点（不含 L0）。"""
    if not seeds or max_levels < 1:
        return []
    all_summaries: list[RaptorSummary] = []
    current = seeds
    for level in range(1, max_levels + 1):
        if len(current) < min_cluster_size * 2:
            break
        vectors = np.asarray([s.embedding for s in current], dtype=float)
        k = _pick_k(len(current))
        if k <= 1:
            break
        labels = _kmeans(vectors, k)
        clusters: dict[int, list[RaptorSeed]] = {}
        for seed, lbl in zip(current, labels):
            clusters.setdefault(int(lbl), []).append(seed)

        level_summaries: list[RaptorSummary] = []
        for members in clusters.values():
            if len(members) < min_cluster_size:
                continue
            try:
                summary_text = await summarize_fn([m.content for m in members])
            except Exception as exc:
                logger.warning("raptor_summarize_failed", level=level, error=str(exc)[:200])
                continue
            if not summary_text or not summary_text.strip():
                continue
            level_summaries.append(RaptorSummary(
                id=uuid.uuid4(),
                summary=summary_text.strip(),
                member_ids=[m.id for m in members],
                level=level,
            ))

        if not level_summaries:
            break
        # 为下一层 embed 本层 summary（下一层的 RaptorSeed）
        try:
            vecs = await embed_fn([s.summary for s in level_summaries])
        except Exception as exc:
            logger.warning("raptor_embed_failed", level=level, error=str(exc)[:200])
            # 无法 embed 就停在本层
            all_summaries.extend(level_summaries)
            break
        for s, v in zip(level_summaries, vecs):
            s.embedding = np.asarray(v, dtype=float)
        all_summaries.extend(level_summaries)

        # 下一轮用本层 summary 作为 seed
        current = [
            RaptorSeed(id=s.id, content=s.summary, embedding=s.embedding)
            for s in level_summaries if s.embedding is not None
        ]
    return all_summaries


# ─── 默认 summarize_fn — 系统默认 LLM ─────────────────────────────

_SUMMARIZE_SYSTEM = (
    "你是一名知识管理助手。将多个文档片段压缩为一个涵盖其核心内容的简明摘要，"
    "保留关键事实与术语，去除冗余与寒暄。字数 150 字以内，保持原文语言。"
)


def _build_summarize_prompt(texts: list[str]) -> str:
    joined = "\n\n---\n\n".join(
        f"[片段 {i+1}]\n{t.strip()[:2000]}" for i, t in enumerate(texts[:10])
    )
    return f"请对以下片段生成一个整合摘要：\n\n{joined}"


def build_default_summarize_fn():
    """返回一个调系统默认 LLM 的 async summarize 函数。"""
    async def _summarize(texts: list[str]) -> str:
        from app.core.database import async_session
        from app.model.service import ModelService
        from app.system.models import SystemSettings

        async with async_session() as db:
            row = await db.get(SystemSettings, 1)
            settings_dict = (row.settings or {}) if row else {}
            reg_id = settings_dict.get("default_llm_model_id")
            if not reg_id:
                raise RuntimeError("系统未配置默认 LLM，无法执行 RAPTOR 摘要")
            svc = ModelService(db)
            resp = await svc.chat_by_registry(
                uuid.UUID(str(reg_id)),
                [
                    {"role": "system", "content": _SUMMARIZE_SYSTEM},
                    {"role": "user", "content": _build_summarize_prompt(texts)},
                ],
            )
        choices = resp.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content") or ""

    return _summarize


def build_default_embed_fn(kb_id: uuid.UUID):
    """为指定 KB 返回一个 async embed 函数，使用 KB 配置的 embedding 模型。"""
    async def _embed(texts: list[str]) -> list[list[float]]:
        from app.core.database import async_session
        from app.knowledge.models import KnowledgeBase
        from app.model.service import ModelService

        async with async_session() as db:
            kb = await db.get(KnowledgeBase, kb_id)
            if kb is None:
                raise RuntimeError(f"KB {kb_id} 不存在")
            svc = ModelService(db)
            if kb.embedding_model_id:
                return await svc.embed_by_registry(kb.embedding_model_id, texts)
            if kb.embedding_provider_id and kb.embedding_model_name:
                return await svc.embed(kb.embedding_provider_id, kb.embedding_model_name, texts)
            raise RuntimeError(f"KB {kb_id} 未配置 embedding")

    return _embed
