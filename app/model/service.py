"""ModelService — unified façade over the Provider Adapter layer.

Public API is unchanged from the LiteLLM-centric version: ``chat``,
``chat_stream``, ``embed``, ``rerank``, plus the registry/discovery helpers.
Internally every call now routes to ``get_provider_impl(provider.type)``.

LiteLLM is retained only as:
- ``litellm.completion_cost`` / ``token_counter`` — pure-function utilities
- ``LiteLLMFallbackProvider`` — long-tail vendors (Bedrock, Vertex, Cohere, ...)
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import litellm
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.models import CostRecord, ModelProvider, ModelRegistryEntry
from app.model.providers import get_provider_impl
from app.model.schemas import (
    ProviderCreate,
    ProviderUpdate,
    RegistryEntryCreate,
    RegistryEntryResponse,
    RegistryEntryUpdate,
)

logger = structlog.get_logger(__name__)


class ModelService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Provider CRUD ─────────────────────────────────────────────

    async def create_provider(
        self, data: ProviderCreate, created_by: uuid.UUID,
    ) -> ModelProvider:
        provider = ModelProvider(
            name=data.name,
            type=data.type,
            base_url=data.base_url,
            api_key=data.api_key,
            extra_config=data.extra_config,
            models_available=data.models_available.model_dump(),
            default_llm_model=data.default_llm_model,
            default_embedding_model=data.default_embedding_model,
            created_by=created_by,
        )
        self.db.add(provider)
        await self.db.flush()
        await self.db.refresh(provider)
        return provider

    async def get_provider(self, provider_id: uuid.UUID) -> ModelProvider | None:
        return await self.db.get(ModelProvider, provider_id)

    async def list_providers(self, active_only: bool = False) -> list[ModelProvider]:
        stmt = select(ModelProvider)
        if active_only:
            stmt = stmt.where(ModelProvider.is_active.is_(True))
        result = await self.db.execute(stmt.order_by(ModelProvider.created_at))
        return list(result.scalars().all())

    async def update_provider(
        self, provider_id: uuid.UUID, data: ProviderUpdate,
    ) -> ModelProvider:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")
        update_data = data.model_dump(exclude_unset=True)
        if "models_available" in update_data and update_data["models_available"] is not None:
            update_data["models_available"] = data.models_available.model_dump()
        for key, value in update_data.items():
            setattr(provider, key, value)
        await self.db.flush()
        await self.db.refresh(provider)
        await self._invalidate_cache(provider_id)
        return provider

    async def delete_provider(self, provider_id: uuid.UUID) -> None:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")
        await self.db.delete(provider)
        await self.db.flush()
        await self._invalidate_cache(provider_id)

    @staticmethod
    async def _invalidate_cache(provider_id: uuid.UUID) -> None:
        from app.core.cache import CacheService
        cache = CacheService()
        try:
            await cache.invalidate_hot("provider", str(provider_id))
            await cache.invalidate_hot("provider_list")
        finally:
            await cache.close()

    # ── Cost persistence ──────────────────────────────────────────

    async def _record_cost(
        self,
        provider_id: uuid.UUID,
        model_name: str,
        call_type: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
        trace_id: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> None:
        try:
            record = CostRecord(
                provider_id=provider_id,
                model_name=model_name,
                call_type=call_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                trace_id=trace_id,
                user_id=user_id,
            )
            self.db.add(record)
            await self.db.flush()
        except Exception:
            logger.warning("cost_record_failed", model=model_name, call_type=call_type)

    @staticmethod
    def _safe_cost(model: str, in_tok: int, out_tok: int) -> float:
        """Compute cost via LiteLLM price map; never raise."""
        try:
            return litellm.completion_cost(
                model=model, prompt_tokens=in_tok, completion_tokens=out_tok,
            )
        except Exception:
            logger.debug("cost_tracking_failed", model=model)
            return 0.0

    # ── Provider-backed calls ────────────────────────────────────

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

        impl = get_provider_impl(provider.type)
        response = await impl.chat(
            model=model_name,
            messages=messages,
            base_url=provider.base_url,
            api_key=provider.api_key,
            _type_hint=provider.type,
            **(provider.extra_config or {}),
            **kwargs,
        )

        usage = response.get("usage") or {}
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        cost = self._safe_cost(model_name, in_tok, out_tok)

        await self._record_cost(
            provider_id=provider_id,
            model_name=model_name,
            call_type="chat",
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
            trace_id=kwargs.get("trace_id"),
            user_id=kwargs.get("user_id"),
        )
        return response

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
        impl = get_provider_impl(provider.type)

        logger.info(
            "llm_stream_start",
            type=provider.type, model=model_name, base_url=provider.base_url,
        )
        in_tok = out_tok = 0
        chunk_count = 0
        first_chunks: list[dict] = []
        try:
            async for data in impl.chat_stream(
                model=model_name,
                messages=messages,
                base_url=provider.base_url,
                api_key=provider.api_key,
                _type_hint=provider.type,
                **(provider.extra_config or {}),
                **kwargs,
            ):
                chunk_count += 1
                if chunk_count <= 3:
                    first_chunks.append(data)
                usage = data.get("usage")
                if usage:
                    in_tok = usage.get("prompt_tokens", 0)
                    out_tok = usage.get("completion_tokens", 0)
                yield data
        except Exception:
            logger.exception(
                "llm_stream_failed",
                type=provider.type, model=model_name,
                chunks_received=chunk_count, first_chunks=first_chunks,
            )
            raise
        logger.info(
            "llm_stream_done",
            type=provider.type, model=model_name,
            chunks=chunk_count, in_tok=in_tok, out_tok=out_tok,
        )

        await self._record_cost(
            provider_id=provider_id,
            model_name=model_name,
            call_type="chat_stream",
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=self._safe_cost(model_name, in_tok, out_tok),
            trace_id=kwargs.get("trace_id"),
            user_id=kwargs.get("user_id"),
        )

    async def embed(
        self,
        provider_id: uuid.UUID,
        model_name: str,
        texts: list[str],
    ) -> list[list[float]]:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")

        # L3 cache: single-text queries
        cache = None
        if len(texts) == 1:
            from app.core.cache import CacheService
            cache = CacheService()
            try:
                cached = await cache.get_embedding(model_name, texts[0])
                if cached:
                    await cache.close()
                    return [cached]
            except Exception:
                pass

        impl = get_provider_impl(provider.type)
        vectors = await impl.embed(
            model=model_name,
            texts=texts,
            base_url=provider.base_url,
            api_key=provider.api_key,
            _type_hint=provider.type,
            **(provider.extra_config or {}),
        )

        in_tok = sum(len(t) // 4 for t in texts)  # rough
        await self._record_cost(
            provider_id=provider_id,
            model_name=model_name,
            call_type="embed",
            input_tokens=in_tok,
            cost=self._safe_cost(model_name, in_tok, 0),
        )

        if cache is not None:
            try:
                await cache.set_embedding(vectors[0], model_name, texts[0])
            except Exception:
                pass
            finally:
                await cache.close()
        return vectors

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
        impl = get_provider_impl(provider.type)
        results = await impl.rerank(
            model=model_name,
            query=query,
            documents=documents,
            base_url=provider.base_url,
            api_key=provider.api_key,
            top_n=top_n,
        )
        await self._record_cost(
            provider_id=provider_id,
            model_name=model_name,
            call_type="rerank",
        )
        return results

    # ── Capabilities / discovery / test ──────────────────────────

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

    async def discover_models(
        self, type: str, base_url: str | None, api_key: str | None,
    ) -> list[dict]:
        impl = get_provider_impl(type)
        return await impl.discover_models(
            type_=type, base_url=base_url, api_key=api_key,
        )

    async def test_connectivity(self, provider_id: uuid.UUID) -> dict:
        """Ping the provider with a real LLM + embedding model and return per-
        capability status. Since models are managed via ``ModelRegistryEntry``
        now (not ``provider.models_available``), we discover a representative
        model of each type from the registry. Falls back to the legacy
        ``models_available`` dict / ``default_*_model`` fields if present.
        """
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")
        impl = get_provider_impl(provider.type)

        # Discover one enabled model of each type from the registry.
        registry_rows = (await self.db.execute(
            select(ModelRegistryEntry).where(
                ModelRegistryEntry.provider_id == provider_id,
                ModelRegistryEntry.is_enabled.is_(True),
            )
        )).scalars().all()
        by_type = {"llm": [], "embedding": [], "reranker": []}
        for r in registry_rows:
            by_type.setdefault(r.model_type, []).append(r.model_id)

        legacy = provider.models_available or {}
        llm_model = (
            provider.default_llm_model
            or (by_type["llm"][0] if by_type["llm"] else None)
            or (legacy.get("llm", [None])[0] if legacy.get("llm") else None)
        )
        emb_model = (
            provider.default_embedding_model
            or (by_type["embedding"][0] if by_type["embedding"] else None)
            or (legacy.get("embedding", [None])[0] if legacy.get("embedding") else None)
        )

        result: dict = {}

        if llm_model:
            try:
                await impl.chat(
                    model=llm_model,
                    messages=[{"role": "user", "content": "ping"}],
                    base_url=provider.base_url,
                    api_key=provider.api_key,
                    _type_hint=provider.type,
                    max_tokens=5,
                    **(provider.extra_config or {}),
                )
                result["llm"] = "ok"
                result["llm_detail"] = f"tested with {llm_model}"
            except Exception as e:
                result["llm"] = "error"
                result["llm_detail"] = f"{llm_model}: {str(e)[:280]}"
        else:
            result["llm"] = "skipped"
            result["llm_detail"] = "no LLM model registered for this provider"

        if emb_model:
            try:
                await impl.embed(
                    model=emb_model,
                    texts=["test"],
                    base_url=provider.base_url,
                    api_key=provider.api_key,
                    _type_hint=provider.type,
                    **(provider.extra_config or {}),
                )
                result["embedding"] = "ok"
                result["embedding_detail"] = f"tested with {emb_model}"
            except Exception as e:
                result["embedding"] = "error"
                result["embedding_detail"] = f"{emb_model}: {str(e)[:280]}"
        else:
            result["embedding"] = "skipped"
            result["embedding_detail"] = "no Embedding model registered for this provider"

        return result

    # ── Registry ─────────────────────────────────────────────────

    async def list_registry(
        self,
        model_type: str | None = None,
        provider_id: uuid.UUID | None = None,
        enabled_only: bool = False,
    ) -> list[dict]:
        stmt = select(ModelRegistryEntry, ModelProvider.name.label("provider_name")).join(
            ModelProvider, ModelRegistryEntry.provider_id == ModelProvider.id,
        )
        if model_type:
            stmt = stmt.where(ModelRegistryEntry.model_type == model_type)
        if provider_id:
            stmt = stmt.where(ModelRegistryEntry.provider_id == provider_id)
        if enabled_only:
            stmt = stmt.where(ModelRegistryEntry.is_enabled.is_(True))
        stmt = stmt.order_by(ModelRegistryEntry.model_type, ModelRegistryEntry.model_id)
        rows = (await self.db.execute(stmt)).all()
        return [
            {**RegistryEntryResponse.model_validate(r[0]).model_dump(), "provider_name": r[1]}
            for r in rows
        ]

    async def create_registry_entry(self, data: RegistryEntryCreate) -> ModelRegistryEntry:
        entry = ModelRegistryEntry(
            provider_id=data.provider_id,
            model_id=data.model_id,
            display_name=data.display_name,
            model_type=data.model_type,
            is_enabled=data.is_enabled,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def update_registry_entry(
        self, entry_id: uuid.UUID, data: RegistryEntryUpdate,
    ) -> ModelRegistryEntry:
        entry = await self.db.get(ModelRegistryEntry, entry_id)
        if entry is None:
            raise ValueError("Model not found in registry")
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(entry, k, v)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def delete_registry_entry(self, entry_id: uuid.UUID) -> None:
        entry = await self.db.get(ModelRegistryEntry, entry_id)
        if entry is None:
            raise ValueError("Model not found in registry")
        await self.db.delete(entry)
        await self.db.flush()

    async def sync_registry(self, provider_id: uuid.UUID) -> list[ModelRegistryEntry]:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise ValueError("Provider not found")

        discovered = await self.discover_models(
            provider.type, provider.base_url, provider.api_key,
        )

        existing = (await self.db.execute(
            select(ModelRegistryEntry).where(
                ModelRegistryEntry.provider_id == provider_id
            )
        )).scalars().all()
        existing_map = {e.model_id: e for e in existing}

        new_entries: list[ModelRegistryEntry] = []
        for m in discovered:
            if m["id"] not in existing_map:
                entry = ModelRegistryEntry(
                    provider_id=provider_id,
                    model_id=m["id"],
                    model_type=m["type_hint"],
                    is_enabled=True,
                )
                self.db.add(entry)
                new_entries.append(entry)

        await self.db.flush()
        for e in new_entries:
            await self.db.refresh(e)
        return new_entries

    async def resolve_model(
        self, registry_id: uuid.UUID,
    ) -> tuple[ModelProvider, str]:
        entry = await self.db.get(ModelRegistryEntry, registry_id)
        if entry is None:
            raise ValueError("Model not found in registry")
        if not entry.is_enabled:
            raise ValueError(f"Model '{entry.model_id}' is disabled")
        provider = await self.get_provider(entry.provider_id)
        if provider is None:
            raise ValueError("Model's provider not found")
        if not provider.is_active:
            raise ValueError(f"Provider '{provider.name}' is inactive")
        return provider, entry.model_id

    # ── Registry-based wrappers (used by Agent/KB paths) ────────

    async def chat_by_registry(
        self, registry_id: uuid.UUID, messages: list[dict], **kwargs,
    ) -> dict:
        provider, model_id = await self.resolve_model(registry_id)
        impl = get_provider_impl(provider.type)
        response = await impl.chat(
            model=model_id,
            messages=messages,
            base_url=provider.base_url,
            api_key=provider.api_key,
            _type_hint=provider.type,
            **(provider.extra_config or {}),
            **kwargs,
        )
        usage = response.get("usage") or {}
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        await self._record_cost(
            provider_id=provider.id,
            model_name=model_id,
            call_type="chat",
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=self._safe_cost(model_id, in_tok, out_tok),
            trace_id=kwargs.get("trace_id"),
            user_id=kwargs.get("user_id"),
        )
        return response

    async def chat_stream_by_registry(
        self, registry_id: uuid.UUID, messages: list[dict], **kwargs,
    ) -> AsyncGenerator[dict, None]:
        provider, model_id = await self.resolve_model(registry_id)
        impl = get_provider_impl(provider.type)

        logger.info(
            "llm_stream_start",
            type=provider.type, model=model_id, base_url=provider.base_url,
        )
        in_tok = out_tok = 0
        chunk_count = 0
        first_chunks: list[dict] = []
        try:
            async for data in impl.chat_stream(
                model=model_id,
                messages=messages,
                base_url=provider.base_url,
                api_key=provider.api_key,
                _type_hint=provider.type,
                **kwargs,
            ):
                chunk_count += 1
                if chunk_count <= 3:
                    first_chunks.append(data)
                usage = data.get("usage")
                if usage:
                    in_tok = usage.get("prompt_tokens", 0)
                    out_tok = usage.get("completion_tokens", 0)
                yield data
        except Exception:
            logger.exception(
                "llm_stream_failed",
                type=provider.type, model=model_id,
                chunks_received=chunk_count, first_chunks=first_chunks,
            )
            raise
        logger.info(
            "llm_stream_done",
            type=provider.type, model=model_id,
            chunks=chunk_count, in_tok=in_tok, out_tok=out_tok,
        )

        await self._record_cost(
            provider_id=provider.id,
            model_name=model_id,
            call_type="chat_stream",
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=self._safe_cost(model_id, in_tok, out_tok),
            trace_id=kwargs.get("trace_id"),
            user_id=kwargs.get("user_id"),
        )

    async def embed_by_registry(
        self, registry_id: uuid.UUID, texts: list[str],
    ) -> list[list[float]]:
        provider, model_id = await self.resolve_model(registry_id)
        impl = get_provider_impl(provider.type)
        return await impl.embed(
            model=model_id,
            texts=texts,
            base_url=provider.base_url,
            api_key=provider.api_key,
            _type_hint=provider.type,
            **(provider.extra_config or {}),
        )
