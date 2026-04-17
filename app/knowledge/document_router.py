import uuid

from fastapi import APIRouter, Body, Depends, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.core.exceptions import NotFoundError, ValidationError
from app.core.runtime_config import get_runtime_config, resolve
from app.knowledge.document_service import DocumentService
from app.core.limiter import limiter
from app.knowledge.ingestion.tasks import process_document
from app.core.tasks import safe_delay
from app.knowledge.milvus.service import MilvusService
from app.knowledge.models import Chunk, Document
from app.knowledge.schemas import DocumentResponse
from app.knowledge.service import KBService
from app.knowledge.storage.minio_service import MinIOService

router = APIRouter(prefix="/knowledge/{kb_id}/documents", tags=["documents"])

DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
DEFAULT_ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".docx", ".doc", ".html", ".htm", ".txt", ".csv", ".pptx", ".xlsx"}

# Extension → expected MIME type prefixes
MIME_WHITELIST: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".md": {"text/"},
    ".markdown": {"text/"},
    ".docx": {"application/vnd.openxmlformats", "application/zip"},
    ".doc": {"application/msword", "application/vnd.ms"},
    ".html": {"text/html"},
    ".htm": {"text/html"},
    ".txt": {"text/plain"},
    ".csv": {"text/csv", "text/plain", "application/csv"},
    ".pptx": {"application/vnd.openxmlformats", "application/zip"},
    ".xlsx": {"application/vnd.openxmlformats", "application/zip"},
}


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def upload_document(
    request: Request,
    kb_id: uuid.UUID,
    file: UploadFile,
    current_user: CurrentUser,
    folder_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    cfg = await get_runtime_config(db)
    max_file_size = resolve(cfg, "upload_limits", "max_file_size_mb", 50) * 1024 * 1024
    allowed_types_str = resolve(cfg, "upload_limits", "allowed_types", "")
    allowed_ext = {t.strip() for t in allowed_types_str.split(",") if t.strip()} if allowed_types_str else DEFAULT_ALLOWED_EXTENSIONS

    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    if not file.filename:
        raise ValidationError("Filename is required")

    import os
    _, ext = os.path.splitext(file.filename.lower())
    if ext not in allowed_ext:
        raise ValidationError(f"File type '{ext}' is not supported")

    file_data = await file.read()
    if len(file_data) > max_file_size:
        raise ValidationError(f"File size exceeds limit ({max_file_size // (1024 * 1024)} MB)")
    if len(file_data) == 0:
        raise ValidationError("Empty file")

    # MIME type verification (best-effort — skip if libmagic unavailable)
    try:
        import magic
        detected_mime = magic.from_buffer(file_data[:8192], mime=True)
        allowed_mimes = MIME_WHITELIST.get(ext, set())
        if allowed_mimes and not any(detected_mime.startswith(prefix) for prefix in allowed_mimes):
            raise ValidationError(f"File content type '{detected_mime}' does not match extension '{ext}'")
    except ImportError:
        pass  # libmagic not installed, rely on extension check only

    doc_svc = DocumentService(db)
    doc = await doc_svc.upload_document(kb_id, folder_id, file.filename, file_data, current_user.id)

    await svc.increment_doc_count(kb_id)

    safe_delay(process_document, str(doc.id))

    return doc


MAX_BATCH_FILES = 20


@router.post("/batch", response_model=list[DocumentResponse], status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def batch_upload_documents(
    request: Request,
    kb_id: uuid.UUID,
    files: list[UploadFile],
    current_user: CurrentUser,
    folder_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if not files:
        raise ValidationError("No files provided")
    if len(files) > MAX_BATCH_FILES:
        raise ValidationError(f"Maximum {MAX_BATCH_FILES} files per batch")

    cfg = await get_runtime_config(db)
    max_file_size = resolve(cfg, "upload_limits", "max_file_size_mb", 50) * 1024 * 1024
    allowed_types_str = resolve(cfg, "upload_limits", "allowed_types", "")
    allowed_ext = {t.strip() for t in allowed_types_str.split(",") if t.strip()} if allowed_types_str else DEFAULT_ALLOWED_EXTENSIONS

    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    import os

    results: list[Document] = []
    errors: list[str] = []

    for file in files:
        if not file.filename:
            errors.append("File with empty filename skipped")
            continue

        _, ext = os.path.splitext(file.filename.lower())
        if ext not in allowed_ext:
            errors.append(f"'{file.filename}': unsupported type '{ext}'")
            continue

        file_data = await file.read()
        if len(file_data) > max_file_size:
            errors.append(f"'{file.filename}': exceeds size limit")
            continue
        if len(file_data) == 0:
            errors.append(f"'{file.filename}': empty file")
            continue

        try:
            import magic
            detected_mime = magic.from_buffer(file_data[:8192], mime=True)
            allowed_mimes = MIME_WHITELIST.get(ext, set())
            if allowed_mimes and not any(detected_mime.startswith(p) for p in allowed_mimes):
                errors.append(f"'{file.filename}': MIME mismatch '{detected_mime}'")
                continue
        except ImportError:
            pass

        try:
            doc_svc = DocumentService(db)
            doc = await doc_svc.upload_document(kb_id, folder_id, file.filename, file_data, current_user.id)
            results.append(doc)
        except Exception as e:
            errors.append(f"'{file.filename}': {str(e)}")

    if results:
        await svc.increment_doc_count(kb_id, delta=len(results))
        for doc in results:
            safe_delay(process_document, str(doc.id))

    if not results and errors:
        raise ValidationError(f"All files failed: {'; '.join(errors)}")

    return results


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


class BatchIdsBody(BaseModel):
    ids: list[uuid.UUID]


class BatchMoveBody(BaseModel):
    ids: list[uuid.UUID]
    target_folder_id: uuid.UUID | None


@router.post("/batch/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def batch_reprocess_documents(
    kb_id: uuid.UUID,
    body: BatchIdsBody,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    if not body.ids:
        raise ValidationError("No document IDs provided")

    for doc_id in body.ids:
        safe_delay(process_document, str(doc_id))

    return {"dispatched": len(body.ids)}


@router.post("/batch/delete", status_code=status.HTTP_204_NO_CONTENT)
async def batch_delete_documents(
    kb_id: uuid.UUID,
    body: BatchIdsBody,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    if not body.ids:
        raise ValidationError("No document IDs provided")

    # Fetch documents to get file paths for MinIO cleanup
    docs = (await db.execute(
        select(Document).where(Document.id.in_(body.ids), Document.knowledge_base_id == kb_id)
    )).scalars().all()

    if not docs:
        raise ValidationError("No matching documents found")

    doc_ids = [d.id for d in docs]
    file_paths = [d.file_path for d in docs if d.file_path]

    # 1. Delete chunks from PG
    await db.execute(
        sa_delete(Chunk).where(Chunk.document_id.in_(doc_ids))
    )

    # 2. Delete vectors from Milvus
    cfg = await get_runtime_config(db)
    collection_name = f"kb_{kb_id}"
    try:
        milvus = MilvusService(runtime_cfg=cfg)
        if milvus.collection_exists(collection_name):
            for did in doc_ids:
                milvus.delete_by_filter(collection_name, f'document_id == "{did}"')
        milvus.close()
    except Exception:
        pass  # best-effort vector cleanup

    # 3. Delete files from MinIO
    minio = MinIOService(cfg)
    for fp in file_paths:
        try:
            await minio.delete(fp)
        except Exception:
            pass  # best-effort file cleanup

    # 4. Delete document records
    await db.execute(
        sa_delete(Document).where(Document.id.in_(doc_ids))
    )

    await svc.increment_doc_count(kb_id, delta=-len(docs))


@router.post("/batch/move", status_code=status.HTTP_204_NO_CONTENT)
async def batch_move_documents(
    kb_id: uuid.UUID,
    body: BatchMoveBody,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    if not body.ids:
        raise ValidationError("No document IDs provided")

    await db.execute(
        sa_update(Document)
        .where(Document.id.in_(body.ids), Document.knowledge_base_id == kb_id)
        .values(folder_id=body.target_folder_id)
    )


@router.post("/{doc_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    doc = await db.get(Document, doc_id)
    if doc is None or doc.knowledge_base_id != kb_id:
        raise ValidationError("Document not found")

    # 1. Delete chunks from PG
    await db.execute(sa_delete(Chunk).where(Chunk.document_id == doc_id))

    # 2. Delete vectors from Milvus (best-effort)
    cfg = await get_runtime_config(db)
    collection_name = f"kb_{kb_id}"
    try:
        milvus = MilvusService(runtime_cfg=cfg)
        if milvus.collection_exists(collection_name):
            milvus.delete_by_filter(collection_name, f'document_id == "{doc_id}"')
        milvus.close()
    except Exception:
        pass

    # 3. Delete file from MinIO (best-effort)
    if doc.file_path:
        try:
            minio = MinIOService(cfg)
            await minio.delete(doc.file_path)
        except Exception:
            pass

    # 4. Delete document record
    await db.delete(doc)
    await svc.increment_doc_count(kb_id, delta=-1)


@router.post("/{doc_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    doc = await db.get(Document, doc_id)
    if doc is None or doc.knowledge_base_id != kb_id:
        raise ValidationError("Document not found")

    safe_delay(process_document, str(doc_id))
    return {"dispatched": 1}


@router.get("/{doc_id}/download")
async def download_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    doc_svc = DocumentService(db)
    doc = await doc_svc.get_document(doc_id)

    cfg = await get_runtime_config(db)
    minio = MinIOService(cfg)
    content = await minio.download(doc.file_path)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.title}"'},
    )


PREVIEW_EXTENSIONS = {".md", ".markdown", ".txt", ".csv"}


@router.get("/{doc_id}/preview")
async def preview_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    doc_svc = DocumentService(db)
    doc = await doc_svc.get_document(doc_id)

    import os
    _, ext = os.path.splitext(doc.title.lower())
    if ext not in PREVIEW_EXTENSIONS:
        raise ValidationError(f"Preview not supported for '{ext}' files")

    cfg = await get_runtime_config(db)
    minio = MinIOService(cfg)
    content = await minio.download(doc.file_path)
    return PlainTextResponse(content.decode("utf-8", errors="replace"))
