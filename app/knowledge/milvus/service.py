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
from app.core.runtime_config import resolve

logger = structlog.get_logger(__name__)


def kb_collection_name(kb_id) -> str:
    """Canonical Milvus collection name for a knowledge base.

    Milvus rejects collection names with characters outside ``[A-Za-z0-9_]``,
    so UUID dashes must be replaced with underscores. This helper is the
    single source of truth — every read / write / delete path that touches
    a KB collection MUST go through it, otherwise writers and readers will
    diverge on the actual collection name and the index becomes invisible.
    """
    return f"kb_{str(kb_id).replace('-', '_')}"


class MilvusService:
    def __init__(self, uri: str | None = None, runtime_cfg: dict | None = None):
        cfg = runtime_cfg or {}
        self._uri = uri or resolve(cfg, "milvus", "uri", settings.MILVUS_URI)
        token = resolve(cfg, "milvus", "token", None)
        kwargs: dict = {"uri": self._uri}
        if token:
            kwargs["token"] = token
        self._client = MilvusClient(**kwargs)

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

    def list_ids(self, collection_name: str, batch_size: int = 10000) -> list[str]:
        """拉一个 collection 的全部主键（id）。Milvus 治理任务用于和 PG
        chunks.id 集合比对。

        实现：用 query_iterator 流式分页（pymilvus 内置），避免一次拉超过
        Milvus 单次 limit（默认 16384）导致截断。"""
        ids: list[str] = []
        try:
            it = self._client.query_iterator(
                collection_name=collection_name,
                batch_size=batch_size,
                filter="",
                output_fields=["id"],
            )
            try:
                while True:
                    batch = it.next()
                    if not batch:
                        break
                    ids.extend(str(r["id"]) for r in batch)
            finally:
                it.close()
        except AttributeError:
            # 老版本 pymilvus 没有 query_iterator，回退到游标分页
            last_id = ""
            while True:
                expr = f'id > "{last_id}"' if last_id else ""
                rows = self._client.query(
                    collection_name=collection_name,
                    filter=expr or "id != ''",
                    output_fields=["id"],
                    limit=batch_size,
                )
                if not rows:
                    break
                ids_batch = [str(r["id"]) for r in rows]
                ids.extend(ids_batch)
                if len(ids_batch) < batch_size:
                    break
                last_id = max(ids_batch)
        logger.info("milvus_list_ids", collection=collection_name, count=len(ids))
        return ids

    def describe_collection(self, collection_name: str) -> dict:
        """返回 collection 的 schema 描述（含 dim / fields）。
        治理对账用：判断 milvus collection 维度 ≟ KB embedding model 维度。"""
        return self._client.describe_collection(collection_name)

    # ── Cleanup ──────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()
