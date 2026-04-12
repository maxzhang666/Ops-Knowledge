import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ModelsAvailable(BaseModel):
    llm: list[str] = []
    embedding: list[str] = []
    reranker: list[str] = []


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(openai_compat|ollama|anthropic)$")
    base_url: str | None = None
    api_key: str | None = None
    models_available: ModelsAvailable = ModelsAvailable()
    default_llm_model: str | None = None
    default_embedding_model: str | None = None


class ProviderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    base_url: str | None = None
    api_key: str | None = None
    models_available: ModelsAvailable | None = None
    default_llm_model: str | None = None
    default_embedding_model: str | None = None
    is_active: bool | None = None


class ProviderResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    base_url: str | None
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
