import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    avatar: str | None = None
    knowledge_base_ids: list[str] | None = None
    folder_ids: list[str] | None = None
    model_provider_id: uuid.UUID
    model_name: str = Field(..., min_length=1, max_length=100)
    system_prompt: str | None = None
    retrieval_config: dict | None = None
    welcome_message: str | None = None
    show_thinking: bool = True
    thinking_detail: str = "normal"
    no_result_mode: str = "honest"
    share_to_dept: bool = True


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    avatar: str | None = None
    knowledge_base_ids: list[str] | None = None
    folder_ids: list[str] | None = None
    model_provider_id: uuid.UUID | None = None
    model_name: str | None = Field(None, min_length=1, max_length=100)
    system_prompt: str | None = None
    retrieval_config: dict | None = None
    welcome_message: str | None = None
    show_thinking: bool | None = None
    thinking_detail: str | None = None
    no_result_mode: str | None = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    avatar: str | None
    agent_type: str
    knowledge_base_ids: list | None
    folder_ids: list | None
    model_provider_id: uuid.UUID
    model_name: str
    system_prompt: str | None
    retrieval_config: dict | None
    welcome_message: str | None
    show_thinking: bool
    thinking_detail: str
    no_result_mode: str
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
