"""MCP Server admin API.

Read endpoints (``list`` / ``get_tools``) are available to any authenticated
user so Agent configuration screens can render the catalog; mutation and
connectivity probes require SYSTEM_ADMIN — MCP servers are infrastructure.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, require_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.core.exceptions import AppError
from app.mcp.schemas import (
    MCPServerCreate,
    MCPServerResponse,
    MCPServerUpdate,
    MCPTool,
    TestConnectionResult,
)
from app.mcp.service import MCPServerService

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/servers", response_model=list[MCPServerResponse])
async def list_servers(
    current_user: CurrentUser,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    svc = MCPServerService(db)
    return await svc.list_servers(active_only=active_only)


@router.get("/servers/{server_id}", response_model=MCPServerResponse)
async def get_server(
    server_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = MCPServerService(db)
    try:
        return await svc.get_server(server_id)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/servers", response_model=MCPServerResponse, status_code=status.HTTP_201_CREATED)
async def create_server(
    data: MCPServerCreate,
    _admin: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    svc = MCPServerService(db)
    return await svc.create_server(data, created_by=_admin.id)


@router.post("/servers/{server_id}/update", response_model=MCPServerResponse)
async def update_server(
    server_id: uuid.UUID,
    data: MCPServerUpdate,
    _admin: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    svc = MCPServerService(db)
    try:
        return await svc.update_server(server_id, data)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/servers/{server_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: uuid.UUID,
    _admin: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    svc = MCPServerService(db)
    try:
        await svc.delete_server(server_id)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/servers/{server_id}/test-connection", response_model=TestConnectionResult)
async def test_connection(
    server_id: uuid.UUID,
    _admin: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    svc = MCPServerService(db)
    try:
        return await svc.test_connection(server_id)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/servers/{server_id}/discover-tools", response_model=list[MCPTool])
async def discover_tools(
    server_id: uuid.UUID,
    _admin: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    svc = MCPServerService(db)
    try:
        return await svc.discover_tools(server_id)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get("/servers/{server_id}/tools", response_model=list[MCPTool])
async def get_tools(
    server_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = MCPServerService(db)
    try:
        return await svc.get_tools(server_id)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
