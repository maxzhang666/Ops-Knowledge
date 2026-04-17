import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    avatar: str | None = None
    agent_type: str = Field("simple", pattern="^(simple|workflow|orchestrator)$")
    knowledge_base_ids: list[str] | None = None
    folder_ids: list[str] | None = None
    model_provider_id: uuid.UUID | None = None
    model_name: str | None = Field(None, max_length=100)
    model_id: uuid.UUID | None = None
    system_prompt: str | None = None
    retrieval_config: dict | None = None
    welcome_message: str | None = None
    show_thinking: bool = True
    thinking_detail: str = Field("normal", pattern="^(minimal|normal)$")
    no_result_mode: str = Field("honest", pattern="^(honest|refuse|hybrid)$")
    share_to_dept: bool = True


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    avatar: str | None = None
    knowledge_base_ids: list[str] | None = None
    folder_ids: list[str] | None = None
    model_provider_id: uuid.UUID | None = None
    model_name: str | None = Field(None, min_length=1, max_length=100)
    model_id: uuid.UUID | None = None
    system_prompt: str | None = None
    retrieval_config: dict | None = None
    welcome_message: str | None = None
    show_thinking: bool | None = None
    thinking_detail: str | None = None
    no_result_mode: str | None = None
    share_to_dept: bool | None = None
    is_active: bool | None = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    avatar: str | None
    agent_type: str
    knowledge_base_ids: list[str]
    folder_ids: list[str]
    model_provider_id: uuid.UUID | None
    model_name: str | None
    model_id: uuid.UUID | None
    workflow_id: uuid.UUID | None
    system_prompt: str | None
    retrieval_config: dict | None
    welcome_message: str | None
    show_thinking: bool
    thinking_detail: str
    no_result_mode: str
    is_active: bool
    share_to_dept: bool = False
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("knowledge_base_ids", "folder_ids", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return v if v is not None else []
