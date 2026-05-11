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


def _build_embedding_text(chunk: dict, threshold: int = _CONTEXT_PREFIX_CHAR_THRESHOLD) -> str:
    """Compose the string actually sent to the embedding model.

    短 chunk 拼 metadata.heading（不拼 doc.title 避免命名噪声）；长 chunk
    保持 content 原样。这是 contextual retrieval 的简化变种。

    M6.7 — `threshold` 可被 KB 级 `context_prefix_max_chars` override；
    设 0 关闭。content 已以 heading 开头时跳过 prefix（M6.6 A 合并后产
    生的 chunk 已含 heading，避免 B 再拼一次造成 heading 重复）。
    """
    content = chunk.get("content", "") or ""
    if threshold <= 0 or len(content) >= threshold:
        return content
    heading = ""
    metadata = chunk.get("metadata") or {}
    if isinstance(metadata, dict):
        heading = metadata.get("heading") or ""
    if not heading:
        return content
    # M6.7 — 防 heading 重复：A 合并后产出的 chunk 形如
    # `"## A\n\n## B\n\n正文"`，metadata.heading 取最后一个（"## B"），
    # startswith 只看第一个 heading 抓不准。改用"heading 段后跟空行"
    # 子串判定，覆盖 heading 出现在 content 任意层级的情况。
    if f"{heading}\n\n" in content:
        return content
    return f"{heading}\n\n{content}"


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
