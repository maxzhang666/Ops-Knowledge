import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ModelsAvailable(BaseModel):
    llm: list[str] = []
    embedding: list[str] = []
    reranker: list[str] = []


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., min_length=1, max_length=50)
    base_url: str | None = Field(None, max_length=500)
    api_key: str | None = Field(None, max_length=2000)
    extra_config: dict | None = None  # Provider extras: api_version, aws_region, ...
    models_available: ModelsAvailable = ModelsAvailable()
    default_llm_model: str | None = None
    default_embedding_model: str | None = None


class ProviderUpdate(BaseModel):
    # ``type`` is editable too (previously missing — the field was silently
    # dropped by Pydantic extra=ignore, so changes never reached the backend).
    name: str | None = Field(None, min_length=1, max_length=100)
    type: str | None = Field(None, min_length=1, max_length=50)
    base_url: str | None = Field(None, max_length=500)
    api_key: str | None = Field(None, max_length=2000)
    extra_config: dict | None = None
    models_available: ModelsAvailable | None = None
    default_llm_model: str | None = None
    default_embedding_model: str | None = None
    is_active: bool | None = None

    # Surface unknown fields as 422 instead of silently dropping them — prevents
    # the kind of "network shows PUT but nothing changes" class of bugs.
    model_config = {"extra": "forbid"}


class ProviderResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    base_url: str | None
    api_key: str | None
    extra_config: dict | None
    models_available: dict
    default_llm_model: str | None
    default_embedding_model: str | None
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestResult(BaseModel):
    llm: str
    llm_detail: str | None = None
    embedding: str
    embedding_detail: str | None = None


class CostRecord(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


# ── Model Registry ─────────────────────────────────────────────

class RegistryEntryCreate(BaseModel):
    provider_id: uuid.UUID
    model_id: str = Field(..., min_length=1, max_length=200)
    display_name: str | None = None
    model_type: str = Field(..., pattern="^(llm|embedding|reranker)$")
    is_enabled: bool = True


class RegistryEntryUpdate(BaseModel):
    display_name: str | None = None
    model_type: str | None = Field(None, pattern="^(llm|embedding|reranker)$")
    is_enabled: bool | None = None


class RegistryEntryResponse(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str | None = None
    model_id: str
    display_name: str | None
    model_type: str
    is_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}
