"""Spec 25 Plan B — 自动标签提取 celery 任务。

触发链（2026-05-14 简化后）：
  entry create/edit → embed_unit_chunks → (chain) extract_auto_tags
  extract → 写 entry.auto_tags + chunks.chunk_tags → 结束

历史变更：原设计在 extract 后比较新旧 auto_tag set，变化则 reset chunks.vector_id
并触发二次 embed（Spec 25 §5.1 L1 prefix 注入要求）。该路径已删除——标签不再进
embedding 输入，仅经 chunk_tags 字段参与 L2 filter / L4 boost / L5 routing。
"""
from __future__ import annotations

import asyncio
import uuid

import structlog
from celery import shared_task
from sqlalchemy import create_engine, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge.models import Chunk, KnowledgeBase, KnowledgeEntry
from app.knowledge.tagging.models import KBTagSettings, TagDictionary

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")


def _get_sync_engine():
    return create_engine(SYNC_DB_URL, pool_pre_ping=True)


def _get_async_engine():
    return create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)


@shared_task(
    bind=True,
    name="app.knowledge.tagging.extract_tasks.extract_auto_tags",
    max_retries=2,
    default_retry_delay=120,
    retry_backoff=True,
)
def extract_auto_tags(self, unit_type: str, unit_id: str) -> dict:
    """提取 unit 的 auto_tags，写入 PG，必要时触发重 embed。

    仅支持 unit_type='entry' (Plan B 范围)；document 类型 v2 再做。
    """
    if unit_type != "entry":
        return {"status": "skipped", "reason": "unsupported_unit_type"}

    engine = _get_sync_engine()
    try:
        with Session(engine) as session:
            entry = session.get(KnowledgeEntry, uuid.UUID(unit_id))
            if entry is None:
                return {"status": "error", "message": "entry not found"}

            kb = session.get(KnowledgeBase, entry.knowledge_base_id)
            if kb is None:
                return {"status": "error", "message": "kb not found"}

            settings_row = session.get(KBTagSettings, kb.id)
            # KB 没初始化 settings → 默认按 disabled 处理；后续 KB 编辑会自动 init
            if settings_row is None or not settings_row.auto_tag_enabled:
                return {"status": "skipped", "reason": "auto_tag_disabled"}

            # 字典 canonical 列表（仅 enabled 的）— 供 LLM prompt 引导命名
            canonicals = [
                r.canonical for r in session.execute(
                    select(TagDictionary).where(
                        TagDictionary.kb_id == kb.id,
                        TagDictionary.is_deprecated.is_(False),
                    )
                ).scalars().all()
            ]

            title = entry.title
            content = entry.content
            rejected = set(entry.rejected_auto_tags or [])
            old_auto_tag_set = {
                t.get("tag") for t in (entry.auto_tags or [])
                if isinstance(t, dict) and isinstance(t.get("tag"), str)
            }
            kb_embedding_id = kb.embedding_model_id
            kb_llm_id = settings_row.auto_tag_llm_model_id
            provider = settings_row.auto_tag_provider
            max_n = settings_row.auto_tag_max_per_unit
            threshold = settings_row.auto_tag_confidence_threshold

        # ── async extractor 调用 + DB 写入（独立 session）─────────
        result = asyncio.run(_run_extract(
            kb_id=kb.id,
            provider=provider,
            title=title,
            content=content,
            max_n=max_n,
            threshold=threshold,
            rejected=rejected,
            canonicals=canonicals,
            kb_embedding_id=kb_embedding_id,
            kb_llm_id=kb_llm_id,
            entry_id=uuid.UUID(unit_id),
        ))

        new_auto_tag_set = {r["tag"] for r in result["auto_tags"]}
        changed = old_auto_tag_set != new_auto_tag_set

        # ── PG sync write —— auto_tags + chunks.chunk_tags 重写 ───
        synced_milvus_chunk_ids: list[str] = []
        with Session(engine) as session:
            entry = session.get(KnowledgeEntry, uuid.UUID(unit_id))
            if entry is None:
                return {"status": "error", "message": "entry vanished after extract"}
            entry.auto_tags = result["auto_tags"]

            chunks = session.execute(
                select(Chunk).where(
                    Chunk.unit_type == "entry",
                    Chunk.unit_id == entry.id,
                )
            ).scalars().all()

            # chunk_tags = user_tags ∪ filtered(auto_tags)（顺序：先 user 后 auto，去重）
            user_tags = list(entry.tags or [])
            auto_tags_list = [r["tag"] for r in result["auto_tags"]]
            seen: set[str] = set()
            merged: list[str] = []
            for t in [*user_tags, *auto_tags_list]:
                if isinstance(t, str) and t and t not in seen:
                    seen.add(t)
                    merged.append(t[:64])
            new_chunk_tags = merged or None
            for c in chunks:
                c.chunk_tags = new_chunk_tags

            session.commit()
            chunk_count = len(chunks)
            # 收集 Milvus 待同步 chunk ids（仅已 embed 过的，vector_id 非空）
            if changed:
                synced_milvus_chunk_ids = [
                    str(c.id) for c in chunks if c.vector_id is not None
                ]
                target_chunk_tags = new_chunk_tags or []

        # ── Milvus partial sync —— 仅 chunk_tags 字段，保留 vector ─
        # 标签变化时同步 Milvus 的 chunk_tags array column；vector 不动，避免
        # 重 embed。失败仅警告，不阻塞 PG 主路径（PG 已是 source of truth，
        # 下次 reindex 会修复 Milvus drift）。
        if synced_milvus_chunk_ids:
            try:
                from app.core.runtime_config import get_sync_runtime_config
                from app.knowledge.milvus.service import MilvusService, kb_collection_name
                runtime_cfg = get_sync_runtime_config()
                milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
                try:
                    updated = milvus_svc.update_chunk_tags(
                        kb_collection_name(kb.id),
                        {cid: target_chunk_tags for cid in synced_milvus_chunk_ids},
                    )
                    logger.info(
                        "auto_tags_milvus_synced",
                        unit_id=unit_id, requested=len(synced_milvus_chunk_ids),
                        updated=updated,
                    )
                finally:
                    milvus_svc.close()
            except Exception:
                logger.warning(
                    "auto_tags_milvus_sync_failed", unit_id=unit_id, exc_info=True,
                )

        logger.info(
            "auto_tags_extracted",
            unit_id=unit_id, kb_id=str(kb.id), provider=provider,
            new=len(result["auto_tags"]), changed=changed,
            chunk_count=chunk_count,
        )

        return {
            "status": "completed",
            "unit_id": unit_id,
            "new_tags": len(result["auto_tags"]),
            "changed": changed,
            "milvus_synced": len(synced_milvus_chunk_ids),
        }
    finally:
        engine.dispose()


@shared_task(name="app.knowledge.tagging.extract_tasks.refresh_user_tags")
def refresh_user_tags(unit_type: str, unit_id: str) -> dict:
    """#5 — tags-only 变化路径：仅刷 chunks.chunk_tags（PG）+ Milvus 同步。

    与 extract_auto_tags 的区别：**不调 extractor**（不跑 KeyBERT/LLM），不动
    entry.auto_tags；只重算 user_tags ∪ auto_tags 的合并集合并写回 chunks。
    用于"用户改了手动 tag"这种纯标签操作，避免重 embed 也避免重跑 extractor。
    """
    if unit_type != "entry":
        return {"status": "skipped", "reason": "unsupported_unit_type"}

    engine = _get_sync_engine()
    try:
        target_chunk_tags: list[str] | None = None
        chunk_ids_to_sync: list[str] = []
        kb_id: uuid.UUID | None = None
        with Session(engine) as session:
            entry = session.get(KnowledgeEntry, uuid.UUID(unit_id))
            if entry is None:
                return {"status": "error", "message": "entry not found"}
            kb_id = entry.knowledge_base_id

            user_tags = list(entry.tags or [])
            auto_tags_list = [
                t.get("tag") for t in (entry.auto_tags or [])
                if isinstance(t, dict) and isinstance(t.get("tag"), str)
            ]
            seen: set[str] = set()
            merged: list[str] = []
            for t in [*user_tags, *auto_tags_list]:
                if isinstance(t, str) and t and t not in seen:
                    seen.add(t)
                    merged.append(t[:64])
            target_chunk_tags = merged or None

            chunks = session.execute(
                select(Chunk).where(
                    Chunk.unit_type == "entry",
                    Chunk.unit_id == entry.id,
                )
            ).scalars().all()
            for c in chunks:
                c.chunk_tags = target_chunk_tags
            chunk_ids_to_sync = [str(c.id) for c in chunks if c.vector_id is not None]
            session.commit()

        if chunk_ids_to_sync and kb_id is not None:
            try:
                from app.core.runtime_config import get_sync_runtime_config
                from app.knowledge.milvus.service import MilvusService, kb_collection_name
                runtime_cfg = get_sync_runtime_config()
                milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
                try:
                    milvus_svc.update_chunk_tags(
                        kb_collection_name(kb_id),
                        {cid: (target_chunk_tags or []) for cid in chunk_ids_to_sync},
                    )
                finally:
                    milvus_svc.close()
            except Exception:
                logger.warning(
                    "refresh_user_tags_milvus_sync_failed",
                    unit_id=unit_id, exc_info=True,
                )
        logger.info(
            "refresh_user_tags_done",
            unit_id=unit_id, milvus_synced=len(chunk_ids_to_sync),
        )
        return {
            "status": "completed",
            "unit_id": unit_id,
            "milvus_synced": len(chunk_ids_to_sync),
        }
    finally:
        engine.dispose()


async def _run_extract(
    *,
    kb_id: uuid.UUID,
    provider: str,
    title: str,
    content: str,
    max_n: int,
    threshold: float,
    rejected: set[str],
    canonicals: list[str],
    kb_embedding_id: uuid.UUID | None,
    kb_llm_id: uuid.UUID | None,
    entry_id: uuid.UUID,
) -> dict:
    """异步 extractor 调用 + 归一化 + 阈值 / 黑名单过滤。"""
    from app.knowledge.tagging.extractors.base import ExtractorDeps
    from app.knowledge.tagging.extractors.registry import get_extractor
    from app.knowledge.tagging.normalizer import normalize_tags
    from app.model.service import ModelService

    a_engine = _get_async_engine()
    a_session = async_sessionmaker(a_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with a_session() as db:
            model_svc = ModelService(db)
            extractor = get_extractor(provider)
            deps = ExtractorDeps(
                model_svc=model_svc,
                kb_embedding_registry_id=kb_embedding_id,
                kb_llm_registry_id=kb_llm_id,
                dictionary_canonicals=canonicals,
            )
            candidates = await extractor.extract(
                title=title, content=content, max_n=max_n, deps=deps,
            )
            if not candidates:
                logger.warning(
                    "auto_tag_extractor_returned_zero",
                    provider=provider, dict_size=len(canonicals),
                    hint="check worker logs for llm_extractor_* warnings",
                )

            # 阈值过滤 + rejected 黑名单
            filtered = [
                c for c in candidates
                if c.confidence >= threshold and c.tag not in rejected
            ]
            if candidates and not filtered:
                logger.warning(
                    "auto_tag_all_filtered_by_threshold_or_rejected",
                    candidates=len(candidates), threshold=threshold,
                    rejected_size=len(rejected),
                )

            # 字典 normalize —— 2026-05-15 改：auto 标签也走 allow_create=True，
            # 字典治理改为"事后合并/弃用"模式（spec 25 §3 同步修订）。
            # actor_id=None 让 created_by 为 NULL，admin 在字典页可据此识别"自动创建"。
            normalized = await normalize_tags(
                db, kb_id, [c.tag for c in filtered],
                allow_create=True,
                actor_id=None,  # 自动创建无 actor
            )
            await db.commit()  # normalize 可能查 cache，无需提交内容；幂等

            # 按 normalize 后的 canonical 重新映射 confidence
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            # raw → canonical 映射（normalize 是双轨 + 缓存查询）
            canon_set = set(normalized)
            out_records = []
            seen_canon: set[str] = set()
            for c in filtered:
                # 候选项 c.tag 经 normalize 后等于哪个 canonical？
                # normalize_tags 内部已批量处理，返回值是按输入顺序去重后的 canonical 列表
                # 这里走第二趟单次 normalize 找其映射；canonical 已在 normalized
                # 中存在则视为命中
                # 简化：candidates 中保留顺序，与 normalized 对齐
                pass

            # 重新做一次顺序对齐：normalized 列表与 filtered 是按输入去重映射。
            # 用 lookup：构造 {original_tag: canonical} 通过再调一次 normalize
            from app.knowledge.tagging.normalizer import get_kb_dict_map, canonicalize_input
            mapping = await get_kb_dict_map(db, kb_id)
            for c in filtered:
                key = canonicalize_input(c.tag)
                canonical = mapping.get(key)
                if canonical is None or canonical in seen_canon:
                    continue
                if canonical not in canon_set:
                    continue
                seen_canon.add(canonical)
                out_records.append({
                    "tag": canonical,
                    "confidence": round(c.confidence, 4),
                    "source": c.source,
                    "extracted_at": now_iso,
                })
                if len(out_records) >= max_n:
                    break
            return {"auto_tags": out_records}
    finally:
        await a_engine.dispose()
    # unreachable; placate type checker
    return {"auto_tags": []}
