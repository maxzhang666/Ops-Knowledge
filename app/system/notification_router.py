import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse
from app.system.models import Notification
from app.system.schemas import NotificationResponse
from app.system.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=PaginatedResponse)
async def list_notifications(
    current_user: CurrentUser,
    is_read: bool | None = Query(None),
    type: str | None = Query(None, description="按通知 type 过滤；省略=全部"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """系统通知列表（通知中心独立页面 + Bell dropdown 共用）。"""
    svc = NotificationService(db)
    items, total = await svc.list_notifications(
        current_user.id, is_read, type, page, page_size,
    )
    return PaginatedResponse(
        items=[NotificationResponse.model_validate(n).model_dump(mode="json") for n in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count")
async def unread_count(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = NotificationService(db)
    return {"count": await svc.unread_count(current_user.id)}


@router.post("/{notif_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notif_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    notif = await db.get(Notification, notif_id)
    if notif is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if notif.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your notification")
    svc = NotificationService(db)
    await svc.mark_read(notif_id)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = NotificationService(db)
    await svc.mark_all_read(current_user.id)
