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


class RetrievalTestRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=100)
    folder_ids: list[uuid.UUID] | None = None


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


class RetrievalTestResponse(BaseModel):
    query_used: str
    timing_ms: int
    total: int
    results: list[RetrievalTestResultItem]
    indexed: bool  # whether the KB has any indexed chunks (Milvus collection exists with data)


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

    retrieval_svc = RetrievalService()
    retrieval_kwargs: dict = {
        "query": body.query,
        "kb_ids": [str(kb.id)],
        "top_k": body.top_k,
        "folder_ids": folder_ids_str,
        "reranker_provider_id": retrieval_cfg.get("reranker_provider_id"),
        "reranker_model_name": retrieval_cfg.get("reranker_model_name"),
    }
    if kb.embedding_model_id:
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
        try:
            if resolved_registry_id:
                stream = model_svc.chat_stream_by_registry(resolved_registry_id, messages)
            else:
                stream = model_svc.chat_stream(
                    resolved_provider_id, resolved_model_name, messages,
                )
            async for data in stream:
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {}) or {}
                text = delta.get("content", "")
                if text:
                    yield sse_event("content_delta", {"delta": text})
        except Exception as exc:
            yield sse_event("content_delta", {"delta": f"\n[错误] {str(exc)[:300]}"})
        yield sse_event("message_end", {})

    return StreamingResponse(_gen(), media_type="text/event-stream")
