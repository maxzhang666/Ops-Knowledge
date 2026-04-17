import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    # Spec 22.5 four-mode calling:
    #   False (default) → sync: SSE if Accept:text/event-stream, else blocking JSON
    #   True            → 202 Accepted + POST to callback_url OR poll via /messages/{id}
    async_mode: bool = Field(default=False, alias="async")
    callback_url: str | None = Field(default=None, max_length=500)

    model_config = {"populate_by_name": True}


class ConversationUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    is_pinned: bool | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    agent_id: uuid.UUID
    user_id: uuid.UUID
    message_count: int
    is_pinned: bool
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
