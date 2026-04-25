"""Topic distribution — k-means 聚类 + LLM 打标签（Plan 26 T2）。

复用 ``chunking/raptor.py`` 的 pure-numpy k-means（避免 sklearn 依赖）。
每簇取最靠近簇心的 N 个 chunk 作为代表 → 丢 LLM 生成短标签 + 关键词。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import numpy as np
import structlog

from app.knowledge.chunking.raptor import _kmeans

logger = structlog.get_logger(__name__)


EXAMPLES_PER_CLUSTER = 5
MIN_CLUSTER_SIZE = 3


@dataclass
class TopicCluster:
    cluster_id: int
    label: str
    keywords: list[str]
    size: int
    example_chunk_ids: list[str]


def pick_topic_k(n_chunks: int) -> int:
    """用 sqrt(n/8) 折衷：小库 3-5 个话题；中库 10-15；大库上限 25。"""
    if n_chunks < MIN_CLUSTER_SIZE * 3:
        return 0
    k = max(2, int(np.sqrt(n_chunks / 8)))
    return min(k, 25)


def _closest_to_centroid(
    labels: np.ndarray, vectors: np.ndarray, cluster: int, n: int,
) -> list[int]:
    idxs = np.where(labels == cluster)[0]
    if idxs.size == 0:
        return []
    pts = vectors[idxs]
    centroid = pts.mean(axis=0, keepdims=True)
    dists = np.linalg.norm(pts - centroid, axis=1)
    order = np.argsort(dists)[:n]
    return [int(idxs[i]) for i in order]


_LABEL_SYSTEM = (
    "你是知识库话题分析师。根据以下代表性片段，为这个话题簇生成："
    '严格 JSON：{"label": "<12 字以内的主题短语>", "keywords": ["<关键词1>","<关键词2>","<关键词3>"]}'
    "。label 应概括全部片段的共同主题；keywords 2-5 个，名词短语。"
)


def _build_label_prompt(texts: list[str]) -> str:
    joined = "\n\n".join(
        f"[片段 {i+1}]\n{t.strip()[:800]}" for i, t in enumerate(texts)
    )
    return f"以下是某话题簇的代表性片段：\n\n{joined}"


def _parse_label_response(text: str) -> tuple[str, list[str]]:
    body = (text or "").strip()
    parsed: dict = {}
    # 3 层解析容错（strict → fence → regex）
    try:
        parsed = json.loads(body)
    except Exception:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(1))
            except Exception:
                parsed = {}
        if not parsed:
            m2 = re.search(r"\{[\s\S]*\}", body)
            if m2:
                try:
                    parsed = json.loads(m2.group(0))
                except Exception:
                    parsed = {}
    label = (parsed.get("label") if isinstance(parsed, dict) else None) or ""
    keywords_raw = parsed.get("keywords") if isinstance(parsed, dict) else None
    keywords: list[str] = []
    if isinstance(keywords_raw, list):
        for item in keywords_raw:
            if isinstance(item, str):
                s = item.strip().strip("。,，.")
                if s:
                    keywords.append(s)
    return label.strip()[:200], keywords[:5]


async def build_topics(
    chunk_ids: list[str],
    contents: list[str],
    vectors: np.ndarray,
    *,
    label_fn,   # async ([str]) -> str
    k: int | None = None,
) -> list[TopicCluster]:
    """主流程：聚类 → 对每簇打标签 → 返回 TopicCluster 列表。"""
    if vectors.ndim != 2 or not (len(chunk_ids) == len(contents) == vectors.shape[0]):
        raise ValueError("chunk_ids / contents / vectors length mismatch")
    n = len(chunk_ids)
    if n < MIN_CLUSTER_SIZE * 2:
        return []
    real_k = k if k is not None else pick_topic_k(n)
    if real_k <= 1:
        return []
    labels = _kmeans(vectors.astype(np.float32), real_k)

    clusters: list[TopicCluster] = []
    for c in range(real_k):
        member_idx = np.where(labels == c)[0]
        if member_idx.size < MIN_CLUSTER_SIZE:
            continue
        example_positions = _closest_to_centroid(labels, vectors, c, EXAMPLES_PER_CLUSTER)
        example_texts = [contents[i] for i in example_positions]
        try:
            raw = await label_fn(example_texts)
        except Exception as exc:
            logger.debug("topic_label_failed", cluster=int(c), error=str(exc)[:200])
            raw = ""
        label, keywords = _parse_label_response(raw)
        if not label:
            label = f"话题 {c + 1}"
        clusters.append(TopicCluster(
            cluster_id=int(c),
            label=label,
            keywords=keywords,
            size=int(member_idx.size),
            example_chunk_ids=[chunk_ids[i] for i in example_positions],
        ))
    # 按 size 降序更易读
    clusters.sort(key=lambda t: t.size, reverse=True)
    # 重新编号使 cluster_id 与展示顺序一致
    for new_id, c in enumerate(clusters):
        c.cluster_id = new_id
    return clusters


def build_default_label_fn():
    import uuid as _uuid

    async def _label(texts: list[str]) -> str:
        from app.core.database import async_session
        from app.model.service import ModelService
        from app.system.models import SystemSettings

        async with async_session() as db:
            row = await db.get(SystemSettings, 1)
            cfg = (row.settings or {}) if row else {}
            reg_id = cfg.get("default_llm_model_id")
            if not reg_id:
                raise RuntimeError("系统未配置默认 LLM，无法生成话题标签")
            svc = ModelService(db)
            resp = await svc.chat_by_registry(
                _uuid.UUID(str(reg_id)),
                [
                    {"role": "system", "content": _LABEL_SYSTEM},
                    {"role": "user", "content": _build_label_prompt(texts)},
                ],
            )
        choices = resp.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content") or ""

    return _label
