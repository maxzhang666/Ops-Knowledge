"""Transport-aware MCP server schemas.

``config`` shape is validated against ``transport_type`` so the router
rejects malformed payloads before they hit ``service.py``. Keeping the
union in Pydantic (rather than SQLAlchemy) lets the DB stay JSONB while
the API still surfaces clear 422s.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ── Transport-specific configs ──────────────────────────────────

class StreamableHTTPConfig(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)
    headers: dict[str, str] | None = None


class SSEConfig(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)
    headers: dict[str, str] | None = None


class StdioConfig(BaseModel):
    command: str = Field(..., min_length=1, max_length=500)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None


# ── Auth ─────────────────────────────────────────────────────────
# Separate from ``config`` so creds never land in logs alongside the
# transport URL. Consumed by transport layer as extra headers.

class AuthConfig(BaseModel):
    bearer_token: str | None = None
    api_key: str | None = None
    api_key_header: str | None = "X-API-Key"
    extra_headers: dict[str, str] | None = None


# ── CRUD schemas ─────────────────────────────────────────────────

TRANSPORT_TYPES = {"http", "sse", "stdio"}


def _validate_transport_config(transport_type: str, config: dict) -> dict:
    """Shape-check ``config`` against ``transport_type``. Raises on mismatch
    so the router returns 422 before we persist garbage."""
    if transport_type == "http":
        return StreamableHTTPConfig.model_validate(config).model_dump(exclude_none=True)
    if transport_type == "sse":
        return SSEConfig.model_validate(config).model_dump(exclude_none=True)
    if transport_type == "stdio":
        return StdioConfig.model_validate(config).model_dump(exclude_none=True)
    raise ValueError(f"Unsupported transport_type: {transport_type}")


class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    transport_type: Literal["http", "sse", "stdio"]
    config: dict
    auth_config: AuthConfig | None = None
    enabled_tools: list[str] | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _check_config(self):
        self.config = _validate_transport_config(self.transport_type, self.config)
        return self


class MCPServerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    transport_type: Literal["http", "sse", "stdio"] | None = None
    config: dict | None = None
    auth_config: AuthConfig | None = None
    enabled_tools: list[str] | None = None
    is_active: bool | None = None

    # Unknown keys → 422 rather than silent drop (same pattern as ProviderUpdate)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _check_config(self):
        # When transport or config changes, require both so we can re-validate
        if self.transport_type is not None and self.config is None:
            raise ValueError("config is required when transport_type changes")
        if self.config is not None and self.transport_type is not None:
            self.config = _validate_transport_config(self.transport_type, self.config)
        return self


class MCPTool(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict | None = None


class MCPServerResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    transport_type: str
    config: dict
    auth_config: dict | None
    enabled_tools: list[str] | None
    is_active: bool
    health_status: str | None
    last_checked_at: datetime | None
    discovered_tools: list[dict] | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestConnectionResult(BaseModel):
    ok: bool
    detail: str
    server_info: dict | None = None
