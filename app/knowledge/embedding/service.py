from __future__ import annotations

import json
import uuid

import structlog

from app.knowledge.milvus.service import MilvusService
from app.model.service import ModelService

logger = structlog.get_logger(__name__)


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

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c["content"] for c in batch]

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

            self.milvus_svc.insert(collection_name, rows)
            all_ids.extend(str(c["id"]) for c in batch)

            logger.info(
                "embedding_batch_stored",
                collection=collection_name,
                batch_start=i,
                batch_count=len(batch),
            )

        return all_ids
