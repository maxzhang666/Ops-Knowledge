from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthService
from app.core.database import get_db
from app.system.schemas import InitRequest
from app.system.service import InitService

router = APIRouter(prefix="/system/init", tags=["system-init"])


@router.get("/status")
async def init_status(db: AsyncSession = Depends(get_db)):
    svc = InitService(db)
    return {"needs_init": await svc.needs_init()}


@router.post("", status_code=status.HTTP_201_CREATED)
async def initialize_system(
    data: InitRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = InitService(db)
    try:
        user = await svc.initialize(data.username, data.email, data.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    auth_svc = AuthService(db)
    tokens = auth_svc.create_tokens(user)
    return {"user_id": str(user.id), "username": user.username, **tokens}
