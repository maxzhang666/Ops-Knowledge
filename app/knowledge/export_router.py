import io
import uuid

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.exceptions import ValidationError
from app.knowledge.export_service import ExportService
from app.knowledge.service import KBService

router = APIRouter(prefix="/knowledge", tags=["knowledge-export"])

MAX_IMPORT_SIZE = 500 * 1024 * 1024  # 500 MB


@router.post("/{kb_id}/export")
async def export_kb(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    export_svc = ExportService(db)
    data = await export_svc.export_kb(kb_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{kb.name}.oka"'},
    )


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_kb(
    file: UploadFile,
    current_user: CurrentUser,
    re_chunk: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".oka"):
        raise ValidationError("Only .oka files are accepted")

    archive_data = await file.read()
    if len(archive_data) > MAX_IMPORT_SIZE:
        raise ValidationError(f"File exceeds {MAX_IMPORT_SIZE // (1024 * 1024)} MB limit")

    export_svc = ExportService(db)
    kb_id = await export_svc.import_kb(archive_data, current_user.id, re_chunk)
    return {"kb_id": str(kb_id)}
