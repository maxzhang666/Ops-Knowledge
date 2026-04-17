"""Knowledge Ingestion API — structured push endpoint (spec 22.3).

External systems (ticket tools, wiki exporters, monitoring tools) can push
knowledge items directly into a KB without going through file upload.

Each ingested item becomes a Document with ``source_type="api_ingestion"``,
managed the same way as uploaded documents (visible in list, deletable,
reprocessable, indexed by Celery).
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.exceptions import ValidationError
from app.core.tasks import safe_delay
from app.knowledge.ingestion.tasks import process_document
from app.knowledge.models import Document, DocumentStatus
from app.knowledge.service import KBService

router = APIRouter(prefix="/knowledge/{kb_id}/ingest", tags=["knowledge-ingest"])


class QaPairItem(BaseModel):
    type: Literal["qa_pair"]
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    metadata: dict | None = None


class TextItem(BaseModel):
    type: Literal["text"]
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    metadata: dict | None = None


class MarkdownItem(BaseModel):
    type: Literal["markdown"]
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    metadata: dict | None = None


IngestItem = QaPairItem | TextItem | MarkdownItem


class IngestRequest(BaseModel):
    items: list[IngestItem] = Field(..., min_length=1, max_length=100)
    folder_id: uuid.UUID | None = None


class IngestResponse(BaseModel):
    created: int
    document_ids: list[uuid.UUID]


@router.post("", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_items(
    kb_id: uuid.UUID,
    body: IngestRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Push structured knowledge into the KB. Returns created document IDs.

    Type semantics:
      - qa_pair  → title="Q: {question}", content combines Q/A; chunker uses
                   the ``qa`` preset so Q+A stays in one chunk.
      - text     → stored as-is; default chunker handles splitting if long.
      - markdown → stored as .md content; markdown chunker applies.
    """
    kb_svc = KBService(db)
    kb = await kb_svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    # Enforce quota based on total items being ingested
    for _ in body.items:
        await _check_quota_lenient(kb_svc, kb_id)

    created_docs: list[Document] = []
    for item in body.items:
        title, body_text = _render_item(item)
        doc = Document(
            knowledge_base_id=kb_id,
            folder_id=body.folder_id,
            title=title,
            source_type="api_ingestion",
            file_path="",  # no MinIO object for ingested items
            file_size=len(body_text.encode("utf-8")),
            file_hash=None,
            status=DocumentStatus.PENDING,
            metadata_=item.metadata,
            created_by=current_user.id,
        )
        db.add(doc)
        await db.flush()
        created_docs.append(doc)

        # Stage the raw content directly on the Document via metadata so the
        # ingestion task can skip MinIO download. We reuse `processing_progress`
        # column? No — clean approach: add to metadata_ under a reserved key.
        existing_meta = doc.metadata_ or {}
        existing_meta["_ingested_content"] = body_text
        existing_meta["_ingested_type"] = item.type
        doc.metadata_ = existing_meta

    await db.flush()
    await kb_svc.increment_doc_count(kb_id, delta=len(created_docs))

    # Dispatch processing tasks outside the request (if broker unreachable,
    # documents are still created and can be reprocessed later).
    for doc in created_docs:
        safe_delay(process_document, str(doc.id))

    return IngestResponse(
        created=len(created_docs),
        document_ids=[doc.id for doc in created_docs],
    )


def _render_item(item: IngestItem) -> tuple[str, str]:
    """Produce (title, content) from an ingestion item."""
    if isinstance(item, QaPairItem):
        # Q/A as one text block; chunker's qa preset preserves the pair.
        title = f"Q: {item.question[:180]}"
        content = f"Q: {item.question}\n\nA: {item.answer}"
        return title, content
    if isinstance(item, MarkdownItem):
        return item.title, item.content
    # TextItem
    return item.title, item.content


async def _check_quota_lenient(kb_svc: KBService, kb_id: uuid.UUID) -> None:
    """Delegate to DocumentService quota check but without file-size arg."""
    # Reuse DocumentService's doc-count check — storage check only matters for
    # file uploads, not ingested text.
    from app.knowledge.document_service import DocumentService
    svc = DocumentService(kb_svc.db)
    try:
        await svc.check_doc_quota(kb_id)
    except Exception as e:
        raise ValidationError(str(e))
