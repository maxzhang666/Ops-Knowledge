from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import asdict

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.models import Agent
from app.chat.citations import extract_citations
from app.chat.context import build_context
from app.chat.prompt import assemble_prompt
from app.chat.service import ConversationService
from app.core.config import settings
from app.knowledge.retrieval.service import RetrievalService
from app.model.service import ModelService

logger = structlog.get_logger(__name__)

NO_RESULT_REFUSE_MSG = "Sorry, I could not find relevant information in the knowledge base to answer your question."
NO_RESULT_HONEST_DISCLAIMER = (
    "Note: I did not find directly relevant information in the knowledge base. "
    "The following answer is based on general knowledge and may not be accurate.\n\n"
)
NO_RESULT_HYBRID_DISCLAIMER = (
    "Note: Limited relevant information was found. The answer may include general knowledge.\n\n"
)


async def run_rag_pipeline(
    agent: Agent,
    query: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> AsyncGenerator[tuple[str, dict | str], None]:
    """Execute the RAG pipeline, yielding SSE event tuples.

    CRITICAL: This generator manages its own DB session because
    StreamingResponse returns before the generator is consumed.
    """
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
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
        await conv_svc.add_message(conversation_id, "user", query)
        await db_session.commit()

        trace_id = str(uuid.uuid4())

        yield ("message_start", {
            "conversation_id": str(conversation_id),
            "trace_id": trace_id,
        })

        # Load conversation history
        history_msgs = await conv_svc.get_messages(conversation_id, limit=20)
        history = [
            {"role": m.role, "content": m.content}
            for m in history_msgs
            if m.role in ("user", "assistant")
        ]
        # Exclude the current query from history (last user msg)
        if history and history[-1]["content"] == query:
            history = history[:-1]

        context_str = build_context(history, conv.memory_summary)

        # Retrieval config
        r_cfg = agent.retrieval_config or {}
        kb_ids = agent.knowledge_base_ids or []
        folder_ids = agent.folder_ids or []
        top_k = r_cfg.get("top_k", 5)

        chunks: list[dict] = []
        retrieval_info: dict = {}

        if kb_ids:
            # Need embedding config from retrieval_config
            emb_provider_id = r_cfg.get("embedding_provider_id")
            emb_model_name = r_cfg.get("embedding_model_name")

            if emb_provider_id and emb_model_name:
                retrieval_svc = RetrievalService()
                result = await retrieval_svc.retrieve(
                    query=query,
                    kb_ids=[str(k) for k in kb_ids],
                    embedding_provider_id=uuid.UUID(str(emb_provider_id)),
                    embedding_model_name=emb_model_name,
                    top_k=top_k,
                    folder_ids=[str(f) for f in folder_ids] if folder_ids else None,
                    rewrite=r_cfg.get("rewrite", False),
                    rewrite_history=history[-6:] if r_cfg.get("rewrite") else None,
                    rewrite_provider_id=(
                        uuid.UUID(str(r_cfg["rewrite_provider_id"]))
                        if r_cfg.get("rewrite_provider_id") else None
                    ),
                    rewrite_model_name=r_cfg.get("rewrite_model_name"),
                    reranker_provider_id=(
                        uuid.UUID(str(r_cfg["reranker_provider_id"]))
                        if r_cfg.get("reranker_provider_id") else None
                    ),
                    reranker_model_name=r_cfg.get("reranker_model_name"),
                )

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
                    "query_used": result.query_used,
                    "timing_ms": result.timing_ms,
                    "chunk_count": len(chunks),
                    "total_searched": result.total_searched,
                }

        if retrieval_info:
            yield ("retrieval_info", retrieval_info)

        # No-result handling
        no_result = len(chunks) == 0 and len(kb_ids) > 0
        no_result_mode = agent.no_result_mode or "honest"

        if no_result and no_result_mode == "refuse":
            yield ("content_delta", {"text": NO_RESULT_REFUSE_MSG})
            await conv_svc.add_message(
                conversation_id, "assistant", NO_RESULT_REFUSE_MSG,
                status="completed", trace_id=trace_id,
            )
            await db_session.commit()
            elapsed = int((time.monotonic() - t0) * 1000)
            yield ("message_end", {"status": "completed", "timing_ms": elapsed})
            return

        # Assemble prompt
        prompt_messages = assemble_prompt(
            system_prompt=agent.system_prompt,
            chunks=chunks,
            history=history,
            query=query,
        )

        # Prepend disclaimer for no-result modes
        disclaimer = ""
        if no_result and no_result_mode == "honest":
            disclaimer = NO_RESULT_HONEST_DISCLAIMER
        elif no_result and no_result_mode == "hybrid":
            disclaimer = NO_RESULT_HYBRID_DISCLAIMER

        # Stream LLM response
        full_content = disclaimer
        if disclaimer:
            yield ("content_delta", {"text": disclaimer})

        input_tokens = 0
        output_tokens = 0

        try:
            stream = model_svc.chat_stream(
                agent.model_provider_id,
                agent.model_name,
                prompt_messages,
            )
            async for chunk_data in stream:
                choices = chunk_data.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})

                # Thinking content
                if agent.show_thinking and delta.get("reasoning_content"):
                    yield ("thinking", {"text": delta["reasoning_content"]})

                # Main content
                text = delta.get("content", "")
                if text:
                    full_content += text
                    yield ("content_delta", {"text": text})

                # Token usage (from final chunk)
                usage = chunk_data.get("usage")
                if usage:
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)

        except Exception:
            logger.exception("llm_stream_error", trace_id=trace_id)
            error_msg = "An error occurred while generating the response. Please try again."
            if not full_content.strip():
                full_content = error_msg
                yield ("content_delta", {"text": error_msg})
            yield ("message_end", {"status": "error"})
            await conv_svc.add_message(
                conversation_id, "assistant", full_content,
                status="error", trace_id=trace_id,
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
        }

        # Save assistant message
        await conv_svc.add_message(
            conversation_id, "assistant", full_content,
            status="completed", metadata=metadata,
            token_usage=token_usage, trace_id=trace_id,
        )
        await db_session.commit()

        elapsed = int((time.monotonic() - t0) * 1000)
        yield ("message_end", {
            "status": "completed",
            "timing_ms": elapsed,
            "token_usage": token_usage,
            "cited_sources": cited_sources,
        })

    except Exception:
        logger.exception("pipeline_error")
        yield ("message_end", {"status": "error", "message": "An internal error occurred."})
    finally:
        await db_session.close()
        await engine.dispose()
