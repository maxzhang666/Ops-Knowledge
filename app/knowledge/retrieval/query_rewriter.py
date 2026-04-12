from __future__ import annotations

import uuid

import structlog

from app.core.database import async_session
from app.model.service import ModelService

logger = structlog.get_logger(__name__)

REWRITE_SYSTEM = (
    "You are a query rewriter. Given a conversation history and a follow-up question, "
    "rewrite the follow-up question as a standalone search query. "
    "Output ONLY the rewritten query, nothing else."
)


async def rewrite_query(
    query: str,
    history: list[dict],
    provider_id: uuid.UUID,
    model_name: str,
) -> str:
    if not history:
        return query

    try:
        async with async_session() as session:
            svc = ModelService(session)
            messages = [
                {"role": "system", "content": REWRITE_SYSTEM},
                *history,
                {"role": "user", "content": query},
            ]
            response = await svc.chat(provider_id, model_name, messages, max_tokens=256)
            rewritten = response["choices"][0]["message"]["content"].strip()
            logger.info("query_rewritten", original=query, rewritten=rewritten)
            return rewritten
    except Exception:
        logger.warning("query_rewrite_failed", query=query, exc_info=True)
        return query
