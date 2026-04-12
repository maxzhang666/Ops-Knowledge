import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── KnowledgeBase ────────────────────────────────────────────────

class KBCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    embedding_provider_id: uuid.UUID | None = None
    embedding_model_name: str | None = None
    chunking_config: dict | None = None
    retrieval_config: dict | None = None
    share_to_dept: bool = True


class KBUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    embedding_provider_id: uuid.UUID | None = None
    embedding_model_name: str | None = None
    chunking_config: dict | None = None
    retrieval_config: dict | None = None


class KBResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    embedding_provider_id: uuid.UUID | None
    embedding_model_name: str | None
    chunking_config: dict | None
    retrieval_config: dict | None
    document_count: int
    chunk_count: int
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Folder ───────────────────────────────────────────────────────

class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    parent_folder_id: uuid.UUID | None = None
    position: int = 0


class FolderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    parent_folder_id: uuid.UUID | None = None
    position: int | None = None


class FolderResponse(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    name: str
    parent_folder_id: uuid.UUID | None
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FolderTreeResponse(FolderResponse):
    children: list["FolderTreeResponse"] = []


# ── Document ─────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    folder_id: uuid.UUID | None
    title: str
    source_type: str
    file_size: int
    file_hash: str
    status: str
    error_message: str | None
    processing_progress: dict | None
    chunk_count: int
    token_count: int
    position: int
    is_archived: bool
    version: int
    processed_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
