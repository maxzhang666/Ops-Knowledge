from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import asdict

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.models import Agent
from app.chat.citations import extract_citations
from app.chat.prompt import assemble_prompt, detect_required_vars, format_context_chunks
from app.chat.service import ConversationService
from app.core.config import settings
from app.knowledge.retrieval.service import RetrievalService
from app.model.service import ModelService

logger = structlog.get_logger(__name__)

# Shared engine for pipeline sessions (avoids per-request pool creation)
_pipeline_engine = None


def _get_pipeline_engine():
    global _pipeline_engine
    if _pipeline_engine is None:
        _pipeline_engine = create_async_engine(
            settings.DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10,
        )
    return _pipeline_engine


# No-result handling is now the user's responsibility via prompt authoring.
# See 16-chat-rag-pipeline.md §No-Result Handling — empty retrieval renders
# {{context}} as the EMPTY_CONTEXT_PLACEHOLDER defined in prompt.py; the
# user's prompt decides whether to refuse, answer from general knowledge, etc.


async def run_rag_pipeline(
    agent: Agent,
    query: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> AsyncGenerator[tuple[str, dict | str], None]:
    """Public entry: wrap the RAG pipeline with a Langfuse trace (no-op when
    Langfuse is unconfigured) then delegate to the inner generator.

    Plan 23 Task 2: Simple Agent chat trace. Keeps the inner function intact
    so all existing callers / tests continue to work; observability is added
    as a thin boundary layer."""
    from app.core.observability import capture_io_enabled, get_client

    trace = get_client().trace(
        name="agent.chat",
        user_id=str(user_id) if user_id else None,
        metadata={"agent_id": str(agent.id), "agent_type": agent.agent_type},
        input=query if capture_io_enabled() else None,
    )
    try:
        async for ev in _run_rag_pipeline_inner(
            agent=agent, query=query,
            conversation_id=conversation_id, user_id=user_id,
        ):
            yield ev
    finally:
        try:
            trace.update(
                output={"status": "done"} if capture_io_enabled() else None,
            )
        except Exception:  # noqa: BLE001
            pass


async def _run_rag_pipeline_inner(
    agent: Agent,
    query: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> AsyncGenerator[tuple[str, dict | str], None]:
    """Execute the RAG pipeline, yielding SSE event tuples.

    CRITICAL: This generator manages its own DB session because
    StreamingResponse returns before the generator is consumed.
    """
    engine = _get_pipeline_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    db_session = session_factory()
    try:
        t0 = time.monotonic()
        conv_svc = ConversationService(db_session)
        model_svc = ModelService(db_session)

        # Resolve or create conversation
        if conversation_id:
            conv = await conv_svc.get_conversation(conversation_id)
        else:
            conv = await conv_svc.create_conversation(agent.id, user_id)
            conversation_id = conv.id

        # Save user message
        user_msg = await conv_svc.add_message(conversation_id, "user", query)

        trace_id = str(uuid.uuid4())

        # Create assistant message with status="generating" BEFORE streaming
        # so it persists in DB even if the SSE connection drops.
        assistant_msg = await conv_svc.add_message(
            conversation_id, "assistant", "",
            status="generating", trace_id=trace_id,
        )
        await db_session.commit()

        yield ("message_start", {
            "message_id": str(assistant_msg.id),
            "conversation_id": str(conversation_id),
        })

        # Load conversation history
        # Load history EXCLUDING the user_msg/assistant_msg we just added
        # (they're for DB persistence, not for prompt history).
        exclude_ids = {user_msg.id, assistant_msg.id}
        history_msgs = await conv_svc.get_messages(conversation_id, limit=20)
        history = [
            {"role": m.role, "content": m.content}
            for m in history_msgs
            if m.role in ("user", "assistant") and m.id not in exclude_ids
        ]

        memory_summary = conv.memory_summary

        # Retrieval config
        r_cfg = agent.retrieval_config or {}
        kb_ids = agent.knowledge_base_ids or []
        folder_ids = agent.folder_ids or []
        top_k = r_cfg.get("top_k", 5)

        chunks: list[dict] = []
        retrieval_info: dict = {}

        # E2: Validate provider is active before doing any work
        if agent.model_id:
            try:
                provider, _ = await model_svc.resolve_model(agent.model_id)
            except Exception:
                yield ("content_delta", {"delta": "模型不可用，请检查智能体配置。"})
                yield ("message_end", {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "trace_id": trace_id})
                return
        elif agent.model_provider_id:
            try:
                provider = await model_svc.get_provider(agent.model_provider_id)
                if not provider.is_active:
                    yield ("content_delta", {"delta": "当前模型供应商已被禁用，请在智能体配置中更换模型。"})
                    yield ("message_end", {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "trace_id": trace_id})
                    return
            except Exception:
                yield ("content_delta", {"delta": "模型供应商不可用，请检查智能体配置。"})
                yield ("message_end", {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "trace_id": trace_id})
                return

        # Variable-driven retrieval: run retrieval iff the user's prompt
        # contains {{context}}. This replaces the old "has kb_ids → retrieve"
        # heuristic with explicit prompt-level intent.
        prompt_vars = detect_required_vars(agent.system_prompt or "")
        needs_retrieval = "context" in prompt_vars and bool(kb_ids)
        kb_names: list[str] = []

        # E1: Filter out deleted KBs before retrieval
        if kb_ids:
            from app.knowledge.service import KnowledgeBaseService
            kb_svc = KnowledgeBaseService(db_session)
            valid_kb_ids = []
            for kid in kb_ids:
                try:
                    kb = await kb_svc.get_kb(uuid.UUID(str(kid)))
                    if kb and kb.status != "deleting":
                        valid_kb_ids.append(kid)
                        kb_names.append(kb.name)
                except Exception:
                    pass  # KB deleted or not found, skip
            if not valid_kb_ids and kb_ids:
                logger.warning("agent_all_kbs_deleted", agent_id=str(agent.id))
            kb_ids = valid_kb_ids

        if needs_retrieval and kb_ids:
            yield ("thinking", {"step": 0, "content": "检索知识库..."})

            # Read embedding config from the first KB — prefer registry-based reference
            from app.knowledge.models import KnowledgeBase
            first_kb = await db_session.get(KnowledgeBase, uuid.UUID(str(kb_ids[0])))
            emb_registry_id = first_kb.embedding_model_id if first_kb else None
            emb_provider_id = first_kb.embedding_provider_id if first_kb else None
            emb_model_name = first_kb.embedding_model_name if first_kb else None

            # Merge KB retrieval_config as fallback for rewrite/reranker settings
            kb_r_cfg = (first_kb.retrieval_config or {}) if first_kb else {}

            can_embed = emb_registry_id or (emb_provider_id and emb_model_name)
            if can_embed:
                retrieval_svc = RetrievalService()
                retrieval_kwargs: dict = {
                    "query": query,
                    "kb_ids": [str(k) for k in kb_ids],
                    "top_k": top_k,
                    "folder_ids": [str(f) for f in folder_ids] if folder_ids else None,
                    "rewrite": r_cfg.get("rewrite", kb_r_cfg.get("rewrite", False)),
                    # Plan 30 v2：rewrite_v2 内部裁剪到 8；这里给 8 让长程上下文进入
                    "rewrite_history": history[-8:] if r_cfg.get("rewrite", kb_r_cfg.get("rewrite")) else None,
                    "rewrite_provider_id": (
                        uuid.UUID(str(r_cfg.get("rewrite_provider_id") or kb_r_cfg.get("rewrite_provider_id", "")))
                        if r_cfg.get("rewrite_provider_id") or kb_r_cfg.get("rewrite_provider_id") else None
                    ),
                    "rewrite_model_name": r_cfg.get("rewrite_model_name") or kb_r_cfg.get("rewrite_model_name"),
                    "rewrite_registry_id": (
                        uuid.UUID(str(r_cfg.get("rewrite_registry_id") or kb_r_cfg.get("rewrite_registry_id", "")))
                        if r_cfg.get("rewrite_registry_id") or kb_r_cfg.get("rewrite_registry_id") else None
                    ),
                    # Plan 30 v2：把长期记忆摘要作为 system prefix 进入改写器，
                    # 让多轮深问 / 跨话题指代也能被改写器看见。
                    "rewrite_memory_summary": memory_summary or None,
                    "reranker_provider_id": (
                        uuid.UUID(str(r_cfg.get("reranker_provider_id") or kb_r_cfg.get("reranker_provider_id", "")))
                        if r_cfg.get("reranker_provider_id") or kb_r_cfg.get("reranker_provider_id") else None
                    ),
                    "reranker_model_name": r_cfg.get("reranker_model_name") or kb_r_cfg.get("reranker_model_name"),
                }
                if emb_registry_id:
                    retrieval_kwargs["embedding_model_registry_id"] = emb_registry_id
                else:
                    retrieval_kwargs["embedding_provider_id"] = uuid.UUID(str(emb_provider_id))
                    retrieval_kwargs["embedding_model_name"] = emb_model_name
                result = await retrieval_svc.retrieve(**retrieval_kwargs)

                chunks = [
                    {
                        "content": r.content,
                        "title": r.title,
                        "score": r.score,
                        "document_id": r.document_id,
                        "chunk_id": r.chunk_id,
                        "source_kb_id": r.source_kb_id,
                    }
                    for r in result.results
                ]
                retrieval_info = {
                    "chunks": [
                        {
                            "id": c["chunk_id"],
                            "content_preview": c["content"][:200],
                            "score": round(c["score"], 4),
                            "document_title": c["title"],
                            # Plan 32 — frontend reference panel uses these to deep-link
                            "document_id": c.get("document_id"),
                            "source_kb_id": c.get("source_kb_id"),
                        }
                        for c in chunks
                    ],
                }

        if retrieval_info:
            yield ("retrieval_info", retrieval_info)

        # Dynamic token budget. litellm.get_model_info only knows well-known
        # models; unknown/custom ones quietly fall back to 6000.
        max_ctx = 6000
        try:
            import litellm
            model_key: str | None = None
            if agent.model_id:
                _provider, _model_id_str = await model_svc.resolve_model(agent.model_id)
                model_key = _model_id_str
            elif agent.model_provider_id and agent.model_name:
                model_key = agent.model_name
            if model_key:
                info = litellm.get_model_info(model_key)
                if info and info.get("max_input_tokens"):
                    max_ctx = info["max_input_tokens"]
        except Exception:
            pass  # unknown model — keep fallback, not fatal

        # Build variable dictionary for prompt rendering
        context_budget = int(max_ctx * 0.6)
        variables = {
            "context": format_context_chunks(chunks, context_budget) if "context" in prompt_vars else "",
            "history_summary": memory_summary or "",
            "query": query,
            "knowledge_names": ", ".join(kb_names),
            "kb_count": str(len(kb_ids)),
        }

        prompt_messages = assemble_prompt(
            system_prompt=agent.system_prompt,
            variables=variables,
            history=history,
            query=query,
            max_context_tokens=max_ctx,
        )

        # Stream LLM response
        full_content = ""

        input_tokens = 0
        output_tokens = 0
        thinking_step = 0

        try:
            import asyncio as _asyncio
            if agent.model_id:
                stream = model_svc.chat_stream_by_registry(
                    agent.model_id, prompt_messages,
                )
            else:
                stream = model_svc.chat_stream(
                    agent.model_provider_id, agent.model_name, prompt_messages,
                )
            # Hard per-chunk timeout: if proxy / LiteLLM hang waiting for a
            # chunk, fail fast instead of hanging the SSE connection forever.
            _iter = stream.__aiter__()
            while True:
                try:
                    chunk_data = await _asyncio.wait_for(_iter.__anext__(), timeout=45)
                except StopAsyncIteration:
                    break
                except _asyncio.TimeoutError:
                    raise TimeoutError("LLM stream timed out waiting for next chunk (45s)")
                choices = chunk_data.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})

                # Thinking content — respect thinking_detail level
                if agent.show_thinking and delta.get("reasoning_content"):
                    thinking_step += 1
                    detail_level = agent.thinking_detail or "normal"
                    if detail_level == "minimal":
                        # Minimal: only emit stage labels, not raw reasoning
                        if thinking_step == 1:
                            yield ("thinking", {"step": 1, "content": "分析中..."})
                    else:
                        # Normal: forward LLM reasoning as-is
                        yield ("thinking", {"step": thinking_step, "content": delta["reasoning_content"]})

                # Main content
                text = delta.get("content", "")
                if text:
                    full_content += text
                    yield ("content_delta", {"delta": text})

                # Token usage (from final chunk)
                usage = chunk_data.get("usage")
                if usage:
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)

        except Exception as exc:
            logger.exception("llm_stream_error", trace_id=trace_id)
            # Surface the real reason so users can fix misconfiguration (bad
            # model name, missing api_key, unreachable base_url, etc.)
            detail = str(exc).strip() or exc.__class__.__name__
            error_msg = f"生成出错：{detail[:500]}"
            if not full_content.strip():
                full_content = error_msg
                yield ("content_delta", {"delta": error_msg})
            yield ("message_end", {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "trace_id": trace_id})
            await conv_svc.update_message(
                assistant_msg.id,
                content=full_content,
                status="error",
            )
            await db_session.commit()
            return

        # Post-process: extract citations
        cited_indices = extract_citations(full_content, len(chunks))
        cited_sources = [
            {"index": idx, "title": chunks[idx - 1].get("title", ""), "chunk_id": chunks[idx - 1].get("chunk_id", "")}
            for idx in cited_indices
            if idx <= len(chunks)
        ]

        token_usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        metadata = {
            "cited_sources": cited_sources,
            "chunk_count": len(chunks),
            "retrieval_chunks": [
                {
                    "id": c["chunk_id"],
                    "content_preview": c["content"][:200],
                    "score": round(c["score"], 4),
                    "document_title": c["title"],
                    "document_id": c.get("document_id"),
                    "source_kb_id": c.get("source_kb_id"),
                }
                for c in chunks
            ],
        }

        # Update the pre-created assistant message with final content
        await conv_svc.update_message(
            assistant_msg.id,
            content=full_content,
            status="completed",
            metadata_=metadata,
            token_usage=token_usage,
        )

        # Plan 32 M1.4 — record adopted events for each cited chunk so
        # dynamic scoring sees which chunks the LLM actually used.
        try:
            from app.knowledge.governance.events import record_adopted
            adopted_pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
            for src in cited_sources:
                cid = src.get("chunk_id")
                if not cid:
                    continue
                chunk_entry = next((c for c in chunks if c.get("chunk_id") == cid), None)
                kb_raw = chunk_entry.get("source_kb_id") if chunk_entry else None
                if not kb_raw:
                    continue
                try:
                    adopted_pairs.append((uuid.UUID(cid), uuid.UUID(str(kb_raw))))
                except Exception:
                    continue
            if adopted_pairs:
                await record_adopted(
                    db_session, adopted_pairs,
                    message_id=assistant_msg.id, user_id=user_id,
                )
        except Exception:
            logger.debug("adopted_events_failed", exc_info=True)

        await db_session.commit()

        yield ("message_end", {
            "token_usage": token_usage,
            "trace_id": trace_id,
        })

        # Async post-processing tasks
        from app.chat.tasks import generate_title, summarize_conversation
        from app.core.tasks import safe_delay
        if conv.title is None:
            safe_delay(generate_title, str(conversation_id), query)
        if conv.message_count > 10:
            safe_delay(summarize_conversation, str(conversation_id))
        # Plan 25: LLM-as-judge 评估 —— 异步触发，采样率由 SystemSettings 控制
        if chunks:
            try:
                from app.knowledge.evaluation.tasks import evaluate_message
                safe_delay(evaluate_message, str(assistant_msg.id))
            except Exception:
                logger.debug("evaluate_dispatch_failed", exc_info=True)

    except Exception:
        logger.exception("pipeline_error")
        yield ("message_end", {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "trace_id": ""})
    finally:
        await db_session.close()
        # Do NOT dispose engine — it's a module-level shared pool.
