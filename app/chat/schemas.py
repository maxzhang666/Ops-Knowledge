import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    agent_id: uuid.UUID
    user_id: uuid.UUID
    message_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    status: str | None
    metadata: dict | None = Field(None, alias="metadata_")
    token_usage: dict | None
    trace_id: str | None
    feedback: int | None
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
