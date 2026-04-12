import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.knowledge.retrieval.service import RetrievalService
from app.knowledge.service import KBService

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

    retrieval_cfg = kb.retrieval_config or {}
    folder_ids_str = [str(fid) for fid in body.folder_ids] if body.folder_ids else None

    retrieval_svc = RetrievalService()
    result = await retrieval_svc.retrieve(
        query=body.query,
        kb_ids=[str(kb.id)],
        embedding_provider_id=kb.embedding_provider_id,
        embedding_model_name=kb.embedding_model_name,
        top_k=body.top_k,
        folder_ids=folder_ids_str,
        reranker_provider_id=retrieval_cfg.get("reranker_provider_id"),
        reranker_model_name=retrieval_cfg.get("reranker_model_name"),
    )

    return RetrievalTestResponse(
        query_used=result.query_used,
        timing_ms=result.timing_ms,
        total=len(result.results),
        results=[RetrievalTestResultItem(**asdict(r)) for r in result.results],
    )
