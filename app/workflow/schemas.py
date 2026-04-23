"""Pydantic DTOs for the Workflow API (request / response)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    trigger_type: str = "manual"
    graph_data: dict | None = None  # optional initial draft DSL
    # Plan 31 N2.9 — bind to owning Agent at create time. Orchestrator's
    # rule validator later refuses handler_id that's not owned by itself.
    owner_agent_id: uuid.UUID | None = None


class WorkflowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    graph_data: dict | None = None


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    version: int
    status: str
    trigger_type: str
    graph_data: dict
    published_graph_data: dict | None
    webhook_config: dict | None = None
    owner_agent_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_note: str | None = None


class WorkflowRunRequest(BaseModel):
    """Strict DTO — no silent field drops. See plan 15 review P0 #3."""
    model_config = ConfigDict(extra="forbid")

    inputs: dict | None = None
    # When True, run the current draft graph instead of published_graph_data.
    # Used by the in-editor Debug Panel so authors can iterate without
    # re-publishing after every tweak. Default False preserves the original
    # external-trigger semantics (webhook / API clients hit the published cut).
    from_draft: bool = False
