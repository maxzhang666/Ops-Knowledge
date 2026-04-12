import uuid

from fastapi import APIRouter, Depends, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.core.exceptions import ValidationError
from app.knowledge.document_service import DocumentService
from app.knowledge.ingestion.tasks import process_document
from app.knowledge.schemas import DocumentResponse
from app.knowledge.service import KBService

router = APIRouter(prefix="/knowledge/{kb_id}/documents", tags=["documents"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".docx", ".doc", ".html", ".htm", ".txt", ".csv", ".pptx", ".xlsx"}


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile,
    current_user: CurrentUser,
    folder_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    if not file.filename:
        raise ValidationError("Filename is required")

    import os
    _, ext = os.path.splitext(file.filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"File type '{ext}' is not supported")

    file_data = await file.read()
    if len(file_data) > MAX_FILE_SIZE:
        raise ValidationError(f"File size exceeds limit ({MAX_FILE_SIZE // (1024 * 1024)} MB)")
    if len(file_data) == 0:
        raise ValidationError("Empty file")

    doc_svc = DocumentService(db)
    doc = await doc_svc.upload_document(kb_id, folder_id, file.filename, file_data, current_user.id)

    await svc.increment_doc_count(kb_id)

    process_document.delay(str(doc.id))

    return doc


@router.get("", response_model=PaginatedResponse)
async def list_documents(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    folder_id: uuid.UUID | None = Query(None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    doc_svc = DocumentService(db)
    items, total = await doc_svc.list_documents(
        kb_id, folder_id, pagination.offset, pagination.page_size
    )
    return PaginatedResponse(
        items=[DocumentResponse.model_validate(i) for i in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    doc_svc = DocumentService(db)
    return await doc_svc.get_document(doc_id)
