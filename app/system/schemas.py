import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scope: str = Field(default="all", pattern="^(all|read|knowledge|chat)$")
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    raw_key: str
    key_prefix: str
    scope: str
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InitRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    password: str = Field(..., min_length=8, max_length=72)


class NotificationResponse(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    content: str | None
    priority: str
    is_read: bool
    resource_type: str | None
    resource_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuotaConfig(BaseModel):
    max_kbs_per_user: int = 20
    max_docs_per_kb: int = 500
    max_storage_per_kb_mb: int = 2048
