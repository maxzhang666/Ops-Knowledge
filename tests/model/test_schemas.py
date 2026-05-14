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


def test_provider_response_includes_api_key_for_admin_console():
    """ProviderResponse 显式包含 api_key 明文——这是 admin 密钥管理视图。

    2026-05-14 决策：admin 需要看完整 api_key 以便审计 / 复制 / 验证（系统
    也兼作 key 存储）。安全约束由 router 层 require_role(SYSTEM_ADMIN) 保证；
    所有暴露 ProviderResponse 的 endpoint (create/list/get/update/delete/test)
    都加了 _ADMIN_ONLY dependency。如未来需要给非 admin 显示"已配置"信号，
    应**新增** ProviderPublicView schema（仅 has_api_key:bool），而非放开本表。
    """
    fields = ProviderResponse.model_fields
    assert "api_key" in fields  # 显式契约：admin 视图含完整明文
    assert "name" in fields
    assert "is_active" in fields
