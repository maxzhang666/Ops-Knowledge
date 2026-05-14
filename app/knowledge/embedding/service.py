from __future__ import annotations

import json
import uuid

import structlog

from app.knowledge.milvus.service import MilvusService
from app.model.service import ModelService

logger = structlog.get_logger(__name__)


# M6.6 — 短 chunk contextual prefix 阈值。content 短于此值时，把 metadata
# 里的 heading 拼到 embedding 输入文本前；长 chunk 不动以避免 query/chunk
# 形态不对称。Milvus 里存的 content 字段不变（仅"喂给 embedding 模型"的
# 字符串变了）。
_CONTEXT_PREFIX_CHAR_THRESHOLD = 100


_MAX_TAGS_IN_PREFIX = 10
_MAX_TAG_PREFIX_CHARS = 200


def _build_embedding_text(chunk: dict, threshold: int = _CONTEXT_PREFIX_CHAR_THRESHOLD) -> str:
    """Compose the string actually sent to the embedding model.

    Spec 25 L1：在原有 heading prefix 基础上叠加 tags prefix，结构化为
    `[TAGS] ... [TITLE] ... [CONTENT] ...`，配合 instruct-style embedding
    模型（bge-m3 等）让向量空间编码主题信号。Milvus 中存的 content 字段保持
    原文（searcher 展示用），仅 embedding 输入文本变化。

    顺序：
      1. 若有 chunk_tags → 拼 [TAGS]
      2. 若短 chunk + heading → 拼 [TITLE] heading
      3. 总是带 [CONTENT] content（标记块边界，便于模型分辨）

    无 tags 且无 heading 时退化为原 content（避免 [CONTENT] 标签污染常规
    长 chunk 的 embedding 形态）。
    """
    content = chunk.get("content", "") or ""
    tags = chunk.get("chunk_tags") or []
    if isinstance(tags, (list, tuple)):
        tag_list = [str(t).strip() for t in tags[:_MAX_TAGS_IN_PREFIX] if t]
    else:
        tag_list = []

    # 1. heading prefix（M6.7 行为保留）
    heading = ""
    metadata = chunk.get("metadata") or {}
    if isinstance(metadata, dict):
        heading = metadata.get("heading") or ""
    use_heading = (
        bool(heading) and threshold > 0 and len(content) < threshold
        and f"{heading}\n\n" not in content
    )

    # 2. 无 tags 且无 heading → 完全保留原始 content（M6.6 默认行为）
    if not tag_list and not use_heading:
        return content

    parts: list[str] = []
    if tag_list:
        tag_str = ", ".join(tag_list)[:_MAX_TAG_PREFIX_CHARS]
        parts.append(f"[TAGS] {tag_str}")
    if use_heading:
        parts.append(f"[TITLE] {heading}")
    parts.append(f"[CONTENT] {content}")
    return "\n".join(parts)


class EmbeddingService:
    def __init__(self, model_svc: ModelService, milvus_svc: MilvusService):
        self.model_svc = model_svc
        self.milvus_svc = milvus_svc

    async def embed_and_store(
        self,
        chunks: list[dict],
        collection_name: str,
        provider_id: uuid.UUID | None = None,
        model_name: str | None = None,
        batch_size: int = 64,
        registry_id: uuid.UUID | None = None,
        context_prefix_max_chars: int = _CONTEXT_PREFIX_CHAR_THRESHOLD,
    ) -> list[str]:
        """Embed chunk texts in batches and insert into Milvus.

        Args:
            chunks: list of dicts with keys: id, content, document_id,
                    folder_id, level, position, title, metadata
            collection_name: Milvus collection name
            provider_id: embedding provider UUID (legacy)
            model_name: embedding model name (legacy)
            batch_size: texts per embedding API call
            registry_id: model registry UUID (preferred over provider_id+model_name)

        Returns:
            list of vector_ids (same as chunk ids) successfully stored
        """
        all_ids: list[str] = []
        prefix_applied = 0  # M6.7 — 统计本次 embed 触发了多少次 contextual prefix

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            # M6.6 — 短 chunk 拼 heading prefix 提升 embedding 上下文信号
            texts: list[str] = []
            for c in batch:
                t = _build_embedding_text(c, threshold=context_prefix_max_chars)
                if t != (c.get("content") or ""):
                    prefix_applied += 1
                texts.append(t)

            if registry_id:
                vectors = await self.model_svc.embed_by_registry(registry_id, texts)
            else:
                vectors = await self.model_svc.embed(provider_id, model_name, texts)

            rows = []
            for c, vec in zip(batch, vectors):
                raw_tags = c.get("chunk_tags") or []
                tag_list = [str(t)[:64] for t in raw_tags if t][:20] if isinstance(raw_tags, (list, tuple)) else []
                rows.append({
                    "id": str(c["id"]),
                    "dense_vector": vec,
                    "content": c["content"][:65535],
                    "document_id": str(c.get("document_id", "")),
                    "folder_id": str(c.get("folder_id", "")),
                    "level": c.get("level", 0),
                    "position": c.get("position", 0),
                    "title": c.get("title", "")[:500],
                    "metadata_json": json.dumps(c.get("metadata") or {}, ensure_ascii=False)[:65535],
                    "chunk_tags": tag_list,
                })

            # Use upsert (not insert) so a partially-failed task can retry
            # without hitting Milvus PK conflicts. PG vector_id rebackfill
            # only happens after ALL batches succeed (see embed_document_chunks),
            # so retry restarts from batch 0; previously written batches would
            # collide on insert. upsert overwrites them idempotently.
            self.milvus_svc.upsert(collection_name, rows)
            all_ids.extend(str(c["id"]) for c in batch)

            logger.info(
                "embedding_batch_stored",
                collection=collection_name,
                batch_start=i,
                batch_count=len(batch),
            )

        if chunks:
            logger.info(
                "embedding_contextual_prefix_stats",
                collection=collection_name,
                total=len(chunks),
                prefix_applied=prefix_applied,
                threshold=context_prefix_max_chars,
            )

        return all_ids
