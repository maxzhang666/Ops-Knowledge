import uuid
from collections.abc import AsyncGenerator

import litellm
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.models import ModelProvider
from app.model.schemas import ProviderCreate, ProviderUpdate

logger = structlog.get_logger(__name__)


class ModelService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── CRUD ──────────────────────────────────────────────────────

    async def create_provider(self, data: ProviderCreate, created_by: uuid.UUID) -> ModelProvider:
        provider = ModelProvider(
            name=data.name,
            type=data.type,
            base_url=data.base_url,
            api_key=data.api_key,
            models_available=data.models_available.model_dump(),
            default_llm_model=data.default_llm_model,
            default_embedding_model=data.default_embedding_model,
            created_by=created_by,
        )
        self.db.add(provider)
        await self.db.flush()
        return provider

    async def get_provider(self, provider_id: uuid.UUID) -> ModelProvider | None:
        return await self.db.get(ModelProvider, provider_id)

    async def list_providers(self, active_only: bool = False) -> list[ModelProvider]:
        stmt = select(ModelProvider)
        if active_only:
            stmt = stmt.where(ModelProvider.is_active.is_(True))
        result = await self.db.execute(stmt.order_by(ModelProvider.created_at))
        return list(result.scalars().all())

    async def update_provider(self, provider_id: uuid.UUID, data: ProviderUpdate) -> ModelProvider:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")
        update_data = data.model_dump(exclude_unset=True)
        if "models_available" in update_data and update_data["models_available"] is not None:
            update_data["models_available"] = data.models_available.model_dump()
        for key, value in update_data.items():
            setattr(provider, key, value)
        await self.db.flush()
        return provider

    async def delete_provider(self, provider_id: uuid.UUID) -> None:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")
        await self.db.delete(provider)
        await self.db.flush()

    # ── LiteLLM helpers ──────────────────────────────────────────

    @staticmethod
    def _litellm_model_name(provider: ModelProvider, model_name: str) -> str:
        prefix_map = {
            "openai_compat": "openai",
            "ollama": "ollama",
            "anthropic": "anthropic",
        }
        prefix = prefix_map.get(provider.type, provider.type)
        return f"{prefix}/{model_name}"

    @staticmethod
    def _litellm_kwargs(provider: ModelProvider) -> dict:
        kwargs: dict = {}
        if provider.base_url:
            kwargs["api_base"] = provider.base_url
        if provider.api_key:
            kwargs["api_key"] = provider.api_key
        return kwargs

    # ── LiteLLM wrappers ─────────────────────────────────────────

    async def chat(
        self,
        provider_id: uuid.UUID,
        model_name: str,
        messages: list[dict],
        **kwargs,
    ) -> dict:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")

        model = self._litellm_model_name(provider, model_name)
        llm_kwargs = self._litellm_kwargs(provider)

        response = await litellm.acompletion(
            model=model, messages=messages, **llm_kwargs, **kwargs
        )

        try:
            cost = litellm.completion_cost(completion_response=response)
            usage = response.usage
            logger.info(
                "llm_call_cost",
                model=model_name,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                cost_usd=cost,
            )
        except Exception:
            logger.debug("cost_tracking_failed", model=model_name)

        return response.model_dump()

    async def chat_stream(
        self,
        provider_id: uuid.UUID,
        model_name: str,
        messages: list[dict],
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")

        model = self._litellm_model_name(provider, model_name)
        llm_kwargs = self._litellm_kwargs(provider)

        response = await litellm.acompletion(
            model=model, messages=messages, stream=True, **llm_kwargs, **kwargs
        )
        async for chunk in response:
            yield chunk.model_dump()

    async def embed(
        self,
        provider_id: uuid.UUID,
        model_name: str,
        texts: list[str],
    ) -> list[list[float]]:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")

        model = self._litellm_model_name(provider, model_name)
        llm_kwargs = self._litellm_kwargs(provider)

        response = await litellm.aembedding(model=model, input=texts, **llm_kwargs)
        return [item["embedding"] for item in response.data]

    async def rerank(
        self,
        provider_id: uuid.UUID,
        model_name: str,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[dict]:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")

        model = self._litellm_model_name(provider, model_name)
        llm_kwargs = self._litellm_kwargs(provider)

        response = await litellm.arerank(
            model=model, query=query, documents=documents, top_n=top_n, **llm_kwargs
        )
        return [r.model_dump() for r in response.results]

    async def get_capabilities(self, provider_id: uuid.UUID) -> dict[str, bool]:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")
        models = provider.models_available or {}
        return {
            "llm": bool(models.get("llm")),
            "embedding": bool(models.get("embedding")),
            "reranker": bool(models.get("reranker")),
        }

    async def chat_with_fallback(
        self,
        provider_ids: list[uuid.UUID],
        model_name: str,
        messages: list[dict],
        **kwargs,
    ) -> dict:
        last_error: Exception | None = None
        for pid in provider_ids:
            try:
                return await self.chat(pid, model_name, messages, **kwargs)
            except Exception as e:
                logger.warning("chat_fallback", provider_id=str(pid), error=str(e))
                last_error = e
        raise last_error or ValueError("No providers given")

    async def test_connectivity(self, provider_id: uuid.UUID) -> dict:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")

        caps = await self.get_capabilities(provider_id)
        result: dict = {}

        if caps["llm"]:
            try:
                llm_model = provider.default_llm_model or provider.models_available["llm"][0]
                model = self._litellm_model_name(provider, llm_model)
                llm_kwargs = self._litellm_kwargs(provider)
                await litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                    **llm_kwargs,
                )
                result["llm"] = "ok"
            except Exception as e:
                result["llm"] = "error"
                result["llm_detail"] = str(e)
        else:
            result["llm"] = "skipped"

        if caps["embedding"]:
            try:
                emb_model = provider.default_embedding_model or provider.models_available["embedding"][0]
                model = self._litellm_model_name(provider, emb_model)
                llm_kwargs = self._litellm_kwargs(provider)
                await litellm.aembedding(model=model, input=["test"], **llm_kwargs)
                result["embedding"] = "ok"
            except Exception as e:
                result["embedding"] = "error"
                result["embedding_detail"] = str(e)
        else:
            result["embedding"] = "skipped"

        return result
