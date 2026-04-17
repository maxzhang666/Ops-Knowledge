from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.department.models import DepartmentRole


# --- Department CRUD ---

class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    parent_department_id: uuid.UUID | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class DepartmentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    parent_department_id: uuid.UUID | None
    created_at: datetime
    member_count: int = 0

    model_config = {"from_attributes": True}


class DepartmentTreeResponse(DepartmentResponse):
    children: list[DepartmentTreeResponse] = []


# --- Member Management ---

class MemberAssign(BaseModel):
    user_id: uuid.UUID
    role: DepartmentRole = DepartmentRole.VIEWER
    is_primary: bool = False


class MemberUpdate(BaseModel):
    role: DepartmentRole


class MemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    email: str
    role: DepartmentRole
    is_primary: bool

    model_config = {"from_attributes": True}


# --- Resource Sharing ---

class ResourceShare(BaseModel):
    resource_type: str = Field(..., pattern=r"^[a-z_]+$")
    resource_id: uuid.UUID
    access_level: str = Field(..., pattern=r"^(view|edit|use|full)$")


class ResourceShareResponse(BaseModel):
    id: uuid.UUID
    department_id: uuid.UUID
    resource_type: str
    resource_id: uuid.UUID
    access_level: str
    shared_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
