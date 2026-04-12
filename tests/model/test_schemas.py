import pytest
from pydantic import ValidationError

from app.model.schemas import ProviderCreate, ProviderResponse


def test_provider_create_valid():
    provider = ProviderCreate(
        name="OpenAI", type="openai_compat",
        base_url="https://api.openai.com/v1", api_key="sk-test-key",
        models_available={"llm": ["gpt-4o", "gpt-4o-mini"], "embedding": ["text-embedding-3-small"], "reranker": []},
        default_llm_model="gpt-4o", default_embedding_model="text-embedding-3-small",
    )
    assert provider.name == "OpenAI"
    assert provider.type == "openai_compat"
    assert len(provider.models_available.llm) == 2


def test_provider_create_missing_name_fails():
    with pytest.raises(ValidationError):
        ProviderCreate(type="openai_compat")


def test_provider_response_excludes_api_key():
    fields = ProviderResponse.model_fields
    assert "api_key" not in fields
    assert "name" in fields
    assert "is_active" in fields
