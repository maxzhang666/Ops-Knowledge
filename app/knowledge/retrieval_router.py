import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.chat.prompt import format_context_chunks
from app.chat.streaming import sse_event
from app.core.database import get_db
from app.knowledge.retrieval.service import RetrievalService
from app.knowledge.service import KBService
from app.model.service import ModelService

router = APIRouter(prefix="/knowledge/{kb_id}/retrieval", tags=["retrieval"])


# ── Plan 35 — auto-tuning recommendations endpoint ────────────────


class RetrievalRecoItem(BaseModel):
    query_type: str
    sample_size: int
    payload: dict
    generated_at: str


@router.get("/recommendations", response_model=list[RetrievalRecoItem])
async def list_retrieval_recommendations(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select as _select
    from app.knowledge.retrieval.models import RetrievalRecommendation
    from app.knowledge.service import KBService

    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    rows = (await db.execute(
        _select(RetrievalRecommendation)
        .where(RetrievalRecommendation.kb_id == kb_id)
        .order_by(RetrievalRecommendation.sample_size.desc())
    )).scalars().all()
    return [
        RetrievalRecoItem(
            query_type=r.query_type,
            sample_size=r.sample_size,
            payload=r.payload,
            generated_at=r.generated_at.isoformat(),
        )
        for r in rows
    ]


class RetrievalTestRequest(BaseModel):
    """Workbench M1.4 — full parameter surface so the UI can drive every
    knob the retrieval pipeline supports. All knobs are optional; missing
    values fall back to the KB's `retrieval_config` defaults (or pipeline
    defaults if the KB hasn't customised)."""
    query: str = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=100)
    folder_ids: list[uuid.UUID] | None = None
    bm25_weight: float | None = Field(None, ge=0.0, le=10.0)
    vector_weight: float | None = Field(None, ge=0.0, le=10.0)
    score_threshold: float | None = Field(None, ge=0.0, le=1.0)
    rerank_enabled: bool | None = None  # None = use KB default
    rerank_registry_id: uuid.UUID | None = None  # M6.8 — 临时覆盖 reranker；
    # 仅在 rerank_enabled=True 时生效。None 时回退 KB 默认 reranker
    embedding_registry_id: uuid.UUID | None = None  # override KB embedding
    # Spec 25 L2 — chunk_tags 过滤；{any_of, all_of, not} 任意组合，AND 串联
    tag_filter: dict | None = None
    # Spec 25 L5 — 是否启用 LLM 路由（KB.tag_routing_enabled=true 时才会真正生效）
    enable_tag_routing: bool = True


class RetrievalTestResultItem(BaseModel):
    chunk_id: str
    content: str
    score: float
    document_id: str
    folder_id: str | None
    level: int
    title: str
    metadata: dict
    source_kb_id: str | None
    # Workbench M1.2 — per-stage breakdown for the score column UI
    dense_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None


class RetrievalTestResponse(BaseModel):
    query_used: str
    timing_ms: int
    total: int
    results: list[RetrievalTestResultItem]
    indexed: bool  # whether the KB has any indexed chunks (Milvus collection exists with data)
    # Spec 25 L5 — LLM 路由推断出的 canonical（前端 chip 展示让用户可知 + 可禁用）
    routed_tags: list[str] = []


@router.post("/test", response_model=RetrievalTestResponse)
async def retrieval_test(
    kb_id: uuid.UUID,
    body: RetrievalTestRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    has_embedding = kb.embedding_model_id or (kb.embedding_provider_id and kb.embedding_model_name)
    if not has_embedding:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="知识库未配置 Embedding 模型，请在配置页设置后再测试",
        )

    retrieval_cfg = kb.retrieval_config or {}
    folder_ids_str = [str(fid) for fid in body.folder_ids] if body.folder_ids else None

    # rerank: explicit body flag wins; else fall back to KB config presence
    rerank_on = (
        body.rerank_enabled
        if body.rerank_enabled is not None
        else bool(retrieval_cfg.get("reranker_provider_id") and retrieval_cfg.get("reranker_model_name"))
    )

    retrieval_svc = RetrievalService()
    retrieval_kwargs: dict = {
        "query": body.query,
        "kb_ids": [str(kb.id)],
        "top_k": body.top_k,
        "folder_ids": folder_ids_str,
        "bm25_weight": body.bm25_weight if body.bm25_weight is not None else 1.0,
        "vector_weight": body.vector_weight if body.vector_weight is not None else 1.0,
        "score_threshold": body.score_threshold,
        "created_by": current_user.id,
        # Workbench 检索测试：不算真实使用，跳过治理事件 + retrieval_logs.is_test=True
        "is_test": True,
        "tag_filter": body.tag_filter,
        "enable_tag_routing": body.enable_tag_routing,
    }
    if rerank_on:
        # M6.8 — 临时覆盖优先级：body.rerank_registry_id > KB 默认（provider+model_name）
        if body.rerank_registry_id:
            try:
                model_svc = ModelService(db)
                provider, model_id = await model_svc.resolve_model(body.rerank_registry_id)
                retrieval_kwargs["reranker_provider_id"] = provider.id
                retrieval_kwargs["reranker_model_name"] = model_id
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Reranker 模型解析失败：{exc}",
                )
        else:
            retrieval_kwargs["reranker_provider_id"] = retrieval_cfg.get("reranker_provider_id")
            retrieval_kwargs["reranker_model_name"] = retrieval_cfg.get("reranker_model_name")
    # Embedding override > KB embedding registry > KB legacy provider/name
    if body.embedding_registry_id:
        retrieval_kwargs["embedding_model_registry_id"] = body.embedding_registry_id
    elif kb.embedding_model_id:
        retrieval_kwargs["embedding_model_registry_id"] = kb.embedding_model_id
    else:
        retrieval_kwargs["embedding_provider_id"] = kb.embedding_provider_id
        retrieval_kwargs["embedding_model_name"] = kb.embedding_model_name
    result = await retrieval_svc.retrieve(**retrieval_kwargs)

    return RetrievalTestResponse(
        query_used=result.query_used,
        timing_ms=result.timing_ms,
        total=len(result.results),
        results=[RetrievalTestResultItem(**asdict(r)) for r in result.results],
        indexed=(kb.chunk_count or 0) > 0,
        routed_tags=result.routed_tags,
    )


# ── Workbench M1.4 — retrieval log history ───────────────────────


class RetrievalLogItem(BaseModel):
    id: uuid.UUID
    query: str
    query_type: str
    top_k: int
    result_count: int
    latency_ms: int | None
    params: dict | None
    created_by: uuid.UUID | None
    created_at: str
    is_test: bool = False  # M6.5 — 区分 Workbench 测试 vs 真实使用


@router.get("/logs", response_model=list[RetrievalLogItem])
async def list_retrieval_logs(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    empty: bool | None = None,
    q: str | None = None,
    mine: bool = False,
):
    """Retrieval history feed for the Workbench sidebar.

    Filters:
    - ``empty=true`` → only zero-result runs (knowledge gap diagnosis)
    - ``q=...`` → substring match on stored query
    - ``mine=true`` → only the current user's runs
    """
    from sqlalchemy import select as _select
    from app.knowledge.retrieval.models import RetrievalLog

    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    stmt = (
        _select(RetrievalLog)
        .where(RetrievalLog.kb_id == kb_id)
        .order_by(RetrievalLog.created_at.desc())
    )
    if empty is True:
        stmt = stmt.where(RetrievalLog.result_count == 0)
    if q:
        stmt = stmt.where(RetrievalLog.query.ilike(f"%{q}%"))
    if mine:
        stmt = stmt.where(RetrievalLog.created_by == current_user.id)
    stmt = stmt.limit(max(1, min(limit, 200)))

    rows = (await db.execute(stmt)).scalars().all()
    return [
        RetrievalLogItem(
            id=r.id,
            query=r.query,
            query_type=r.query_type,
            top_k=r.top_k,
            result_count=r.result_count,
            latency_ms=r.latency_ms,
            params=r.params_json,
            created_by=r.created_by,
            created_at=r.created_at.isoformat(),
            is_test=bool(getattr(r, "is_test", False)),
        )
        for r in rows
    ]


class RetrievalThresholdSuggestion(BaseModel):
    """Workbench M6.3 — Baseline floor 阈值建议响应。

    随机抽 30 个已 embed 的 chunk，pairwise cosine 取 P95 作为模型对
    此 KB 的"无关文本对"floor，推荐阈值 = floor + 0.02。`sample_size < 10`
    时返回 None，前端隐藏 chip。
    """
    sample_size: int
    floor: float | None = None
    recommended: float | None = None


def _pairwise_cosine_p95(vectors: list[list[float]]) -> float | None:
    """Compute P95 of pairwise cosine similarities for `vectors`.

    Each pair counted once (i < j). Returns None when fewer than 2 vectors.
    Numpy used for speed: 30 vecs × 1024 dim → 435 pairs in <5ms.
    """
    import numpy as np

    if len(vectors) < 2:
        return None
    mat = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat = mat / norms
    sims = mat @ mat.T  # (N, N) cosine
    iu = np.triu_indices(len(vectors), k=1)
    pairs = sims[iu]
    if pairs.size == 0:
        return None
    return float(np.percentile(pairs, 95))


@router.get("/threshold-suggestion", response_model=RetrievalThresholdSuggestion)
async def get_threshold_suggestion(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Baseline floor: 抽 30 chunk pairwise cosine P95 = 模型 floor，
    推荐阈值 = floor + 0.02。开销 ~50ms（一次 Milvus query + numpy），
    每次请求重算（Workbench 仅打开 + 检索后调用，频率低）。"""
    from sqlalchemy import select as _select
    from sqlalchemy.sql import func as _func
    from app.knowledge.milvus.service import MilvusService, kb_collection_name
    from app.knowledge.models import Chunk

    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    chunk_ids = (await db.execute(
        _select(Chunk.id)
        .where(
            Chunk.knowledge_base_id == kb_id,
            Chunk.vector_id.is_not(None),
            # Plan 39 — 模型 floor 基准不应包含 pending/rejected chunks
            Chunk.review_excluded.is_(False),
        )
        .order_by(_func.random())
        .limit(30)
    )).scalars().all()

    sample_size = len(chunk_ids)
    if sample_size < 10:
        return RetrievalThresholdSuggestion(sample_size=sample_size)

    collection = kb_collection_name(str(kb_id))
    milvus = MilvusService()
    try:
        if not milvus.collection_exists(collection):
            return RetrievalThresholdSuggestion(sample_size=0)
        id_list = ", ".join(f'"{cid}"' for cid in chunk_ids)
        rows = milvus._client.query(
            collection_name=collection,
            filter=f"id in [{id_list}]",
            output_fields=["dense_vector"],
            limit=sample_size,
        )
    finally:
        try:
            milvus.close()
        except Exception:
            pass

    vectors = [r.get("dense_vector") for r in rows if r.get("dense_vector")]
    if len(vectors) < 10:
        return RetrievalThresholdSuggestion(sample_size=len(vectors))

    floor = _pairwise_cosine_p95(vectors)
    if floor is None:
        return RetrievalThresholdSuggestion(sample_size=len(vectors))

    return RetrievalThresholdSuggestion(
        sample_size=len(vectors),
        floor=round(floor, 3),
        recommended=round(min(0.99, floor + 0.02), 3),
    )


class RetrievalLogDetail(RetrievalLogItem):
    """Single log with the full hit-list snapshot (Workbench M2.1).

    The list endpoint stays lean by omitting ``results``; this detail
    endpoint adds it back so the history sidebar can show what the user
    actually saw at the time without re-running the pipeline.
    """
    results: list[RetrievalTestResultItem] = []


# ── Workbench M3 — chunk feedback (👍/👎 from retrieval test results) ──


class RetrievalFeedbackRequest(BaseModel):
    chunk_id: uuid.UUID
    # +1 = relevant / 👍, -1 = not relevant / 👎, 0 = retract previous vote
    sentiment: int = Field(..., ge=-1, le=1)
    log_id: uuid.UUID | None = None  # optional context — which run produced the chunk


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def post_retrieval_feedback(
    kb_id: uuid.UUID,
    body: RetrievalFeedbackRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Record a relevance vote against a single chunk surfaced by retrieval
    test. Writes to ``chunk_usage_events`` via the same governance code path
    chat feedback uses, so the chunk's dynamic quality score (Plan 32 M1)
    picks up the signal on the next rebuild cycle.
    """
    from app.knowledge.governance.events import record_feedback

    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    await record_feedback(
        db,
        [(body.chunk_id, kb_id)],
        sentiment=body.sentiment,
        user_id=current_user.id,
    )
    await db.commit()


@router.get("/logs/{log_id}", response_model=RetrievalLogDetail)
async def get_retrieval_log(
    kb_id: uuid.UUID,
    log_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from app.knowledge.retrieval.models import RetrievalLog

    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    row = await db.get(RetrievalLog, log_id)
    if row is None or row.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="检索记录不存在")

    snapshot = row.results_json or []
    # Older rows (pre-0045) lack the snapshot — return empty list with the
    # rest of the metadata so UI can degrade gracefully ("此条记录无快照，
    # 请重新执行检索").
    return RetrievalLogDetail(
        id=row.id,
        query=row.query,
        query_type=row.query_type,
        top_k=row.top_k,
        result_count=row.result_count,
        latency_ms=row.latency_ms,
        params=row.params_json,
        created_by=row.created_by,
        created_at=row.created_at.isoformat(),
        is_test=bool(getattr(row, "is_test", False)),
        results=[
            RetrievalTestResultItem(
                chunk_id=r.get("chunk_id", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                document_id=r.get("document_id", ""),
                folder_id=r.get("folder_id"),
                level=r.get("level", 0),
                title=r.get("title", ""),
                metadata=r.get("metadata") or {},
                source_kb_id=r.get("source_kb_id"),
                dense_score=r.get("dense_score"),
                bm25_score=r.get("bm25_score"),
                rerank_score=r.get("rerank_score"),
            )
            for r in snapshot
        ],
    )


# ── Quick Q&A (SSE) ──────────────────────────────────────────────
# Editor-facing endpoint: run RAG on a single KB with an ad-hoc LLM,
# stream the answer. No Conversation / Agent / Message rows are created.

class QuickQARequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    model_registry_id: uuid.UUID | None = None
    model_provider_id: uuid.UUID | None = None
    model_name: str | None = None


QA_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question using ONLY the "
    "reference context below. Cite sources using [1], [2] markers. If the "
    "context does not contain the answer, say so plainly.\n\n"
    "Reference context:\n{context}"
)


@router.post("/qa")
async def quick_qa(
    kb_id: uuid.UUID,
    body: QuickQARequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    has_embedding = kb.embedding_model_id or (kb.embedding_provider_id and kb.embedding_model_name)
    if not has_embedding:
        raise HTTPException(400, "知识库未配置 Embedding，无法进行问答")

    # Resolve LLM — body → system default → error
    model_svc = ModelService(db)
    resolved_registry_id = body.model_registry_id
    resolved_provider_id = body.model_provider_id
    resolved_model_name = body.model_name
    if not resolved_registry_id and not (resolved_provider_id and resolved_model_name):
        from app.system.models import SystemSettings
        row = await db.get(SystemSettings, 1)
        default_id = (row.settings or {}).get("default_llm_model_id") if row else None
        if default_id:
            resolved_registry_id = uuid.UUID(str(default_id))
    if not resolved_registry_id and not (resolved_provider_id and resolved_model_name):
        raise HTTPException(400, "未指定 LLM 模型且系统未配置默认 LLM")

    # Pre-flight retrieval (before opening stream) so errors surface as 4xx/5xx
    retrieval_svc = RetrievalService()
    retrieval_kwargs: dict = {
        "query": body.query,
        "kb_ids": [str(kb.id)],
        "top_k": body.top_k,
        # KB 详情快速 QA 是辅助检验工具（在管理界面里"看看效果"），
        # 不是用户的正式问答场景，按测试标志处理
        "is_test": True,
    }
    if kb.embedding_model_id:
        retrieval_kwargs["embedding_model_registry_id"] = kb.embedding_model_id
    else:
        retrieval_kwargs["embedding_provider_id"] = kb.embedding_provider_id
        retrieval_kwargs["embedding_model_name"] = kb.embedding_model_name
    result = await retrieval_svc.retrieve(**retrieval_kwargs)

    chunks = [
        {
            "content": r.content,
            "title": r.title,
            "score": r.score,
            "chunk_id": r.chunk_id,
            "document_id": r.document_id,
        }
        for r in result.results
    ]
    context = format_context_chunks(chunks, max_tokens=4000)
    messages = [
        {"role": "system", "content": QA_SYSTEM_PROMPT.format(context=context)},
        {"role": "user", "content": body.query},
    ]

    async def _gen():
        yield sse_event("retrieval_info", {
            "chunks": [
                {
                    "id": c["chunk_id"],
                    "content_preview": c["content"][:200],
                    "score": round(c["score"], 4),
                    "document_title": c["title"],
                }
                for c in chunks
            ],
        })
        # M5.1 — accumulate token usage across the stream so the UI can
        # show "N prompt + M completion · $0.XXXX" alongside the answer.
        # The provider may emit `usage` either on the final chunk
        # (OpenAI with stream_options.include_usage) or piecemeal — take
        # the latest non-empty value and propagate to message_end.
        prompt_tok = 0
        completion_tok = 0
        emitted_chars = 0
        used_model_name: str | None = None
        try:
            if resolved_registry_id:
                # Resolve the actual model_id name for the message_end
                # payload (registry id alone isn't human-meaningful).
                provider, mid = await model_svc.resolve_model(resolved_registry_id)
                used_model_name = mid
                stream = model_svc.chat_stream_by_registry(resolved_registry_id, messages)
            else:
                used_model_name = resolved_model_name
                stream = model_svc.chat_stream(
                    resolved_provider_id, resolved_model_name, messages,
                )
            async for data in stream:
                usage = data.get("usage") or {}
                if usage:
                    prompt_tok = usage.get("prompt_tokens", prompt_tok) or prompt_tok
                    completion_tok = usage.get("completion_tokens", completion_tok) or completion_tok
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {}) or {}
                text = delta.get("content", "")
                if text:
                    emitted_chars += len(text)
                    yield sse_event("content_delta", {"delta": text})
        except Exception as exc:
            yield sse_event("content_delta", {"delta": f"\n[错误] {str(exc)[:300]}"})

        # Estimate tokens if the provider didn't return usage (rare but
        # happens with some OpenAI-compatible gateways). 4 chars/token is
        # the canonical English heuristic; for CJK content this overstates
        # but it's better than zero.
        if completion_tok == 0 and emitted_chars > 0:
            completion_tok = max(1, emitted_chars // 4)

        cost_usd = 0.0
        if used_model_name and (prompt_tok or completion_tok):
            try:
                import litellm
                cost_usd = litellm.completion_cost(
                    model=used_model_name,
                    prompt_tokens=prompt_tok,
                    completion_tokens=completion_tok,
                ) or 0.0
            except Exception:
                cost_usd = 0.0

        yield sse_event("message_end", {
            "model": used_model_name,
            "tokens": {
                "prompt": prompt_tok,
                "completion": completion_tok,
                "total": prompt_tok + completion_tok,
            },
            "cost_usd": round(float(cost_usd), 6),
        })

    return StreamingResponse(_gen(), media_type="text/event-stream")
