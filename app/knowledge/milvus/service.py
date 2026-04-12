from __future__ import annotations

import structlog
from pymilvus import (
    CollectionSchema,
    DataType,
    FieldSchema,
    Function,
    FunctionType,
    MilvusClient,
)

from app.core.config import settings

logger = structlog.get_logger(__name__)


class MilvusService:
    def __init__(self, uri: str | None = None):
        self._uri = uri or settings.MILVUS_URI
        self._client = MilvusClient(uri=self._uri)

    # ── Collection lifecycle ─────────────────────────────────────

    def create_collection(self, name: str, dim: int) -> None:
        if self._client.has_collection(name):
            logger.info("milvus_collection_exists", name=name)
            return

        schema = CollectionSchema(fields=[
            FieldSchema("id", DataType.VARCHAR, is_primary=True, max_length=100),
            FieldSchema("dense_vector", DataType.FLOAT_VECTOR, dim=dim),
            FieldSchema("sparse_vector", DataType.SPARSE_FLOAT_VECTOR),
            FieldSchema("content", DataType.VARCHAR, max_length=65535, enable_analyzer=True),
            FieldSchema("document_id", DataType.VARCHAR, max_length=100),
            FieldSchema("folder_id", DataType.VARCHAR, max_length=100),
            FieldSchema("level", DataType.INT16),
            FieldSchema("position", DataType.INT32),
            FieldSchema("title", DataType.VARCHAR, max_length=500),
            FieldSchema("metadata_json", DataType.VARCHAR, max_length=65535),
        ])

        bm25_fn = Function(
            name="bm25_fn",
            input_field_names=["content"],
            output_field_names=["sparse_vector"],
            function_type=FunctionType.BM25,
        )
        schema.add_function(bm25_fn)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 256},
        )
        index_params.add_index(
            field_name="sparse_vector",
            index_type="AUTOINDEX",
            metric_type="BM25",
        )
        index_params.add_index(field_name="document_id", index_type="INVERTED")
        index_params.add_index(field_name="folder_id", index_type="INVERTED")
        index_params.add_index(field_name="level", index_type="INVERTED")

        self._client.create_collection(
            collection_name=name, schema=schema, index_params=index_params,
        )
        logger.info("milvus_collection_created", name=name, dim=dim)

    def drop_collection(self, name: str) -> None:
        self._client.drop_collection(name)
        logger.info("milvus_collection_dropped", name=name)

    def list_collections(self) -> list[str]:
        return self._client.list_collections()

    def collection_exists(self, name: str) -> bool:
        return self._client.has_collection(name)

    # ── Data operations ──────────────────────────────────────────

    def insert(self, collection_name: str, data: list[dict]) -> dict:
        result = self._client.insert(collection_name=collection_name, data=data)
        logger.info("milvus_insert", collection=collection_name, count=len(data))
        return result

    def upsert(self, collection_name: str, data: list[dict]) -> dict:
        result = self._client.upsert(collection_name=collection_name, data=data)
        logger.info("milvus_upsert", collection=collection_name, count=len(data))
        return result

    def delete_by_ids(self, collection_name: str, ids: list[str]) -> dict:
        result = self._client.delete(collection_name=collection_name, ids=ids)
        logger.info("milvus_delete_by_ids", collection=collection_name, count=len(ids))
        return result

    def delete_by_filter(self, collection_name: str, filter_expr: str) -> dict:
        result = self._client.delete(collection_name=collection_name, filter=filter_expr)
        logger.info("milvus_delete_by_filter", collection=collection_name, filter=filter_expr)
        return result

    # ── Stats ────────────────────────────────────────────────────

    def get_collection_stats(self, collection_name: str) -> dict:
        return self._client.get_collection_stats(collection_name)

    # ── Cleanup ──────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()
