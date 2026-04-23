"""knowledge_search — queries the Agent's bound KBs.

Uses a fresh session per call via ``ctx.db_factory`` so the tool works
from any execution environment (Workflow node, stand-alone ReAct).
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from app.chat.prompt import format_context_chunks

if TYPE_CHECKING:
    from app.agent.tools import ToolContext


def make_knowledge_search(ctx: "ToolContext") -> BaseTool:
    kb_ids = list(ctx.kb_ids)
    folder_ids = list(ctx.folder_ids)
    db_factory = ctx.db_factory

    @tool
    async def knowledge_search(query: str, top_k: int = 5) -> str:
        """Search the bound knowledge bases for passages relevant to ``query``.
        Returns formatted chunks numbered [1], [2], ... for citing in the answer.

        Use when the question needs factual grounding from the user's
        documents. Prefer 3-5 for focused questions, up to 10 for broad
        research queries.
        """
        if not kb_ids:
            return "No knowledge base is bound to this Agent — cannot search."

        from app.knowledge.models import KnowledgeBase
        from app.knowledge.retrieval.service import RetrievalService

        async with db_factory() as db:
            # Derive embedding config from the first KB (same heuristic as
            # chat pipeline); multi-KB with mixed embeddings is a P2 concern
            first_kb = await db.get(KnowledgeBase, uuid.UUID(str(kb_ids[0])))
            if first_kb is None:
                return f"Knowledge base {kb_ids[0]} not found."

            reg_id = first_kb.embedding_model_id
            prov_id = first_kb.embedding_provider_id
            model_name = first_kb.embedding_model_name

            kwargs: dict = {
                "query": query,
                "kb_ids": [str(k) for k in kb_ids],
                "top_k": max(1, min(top_k, 20)),
                "folder_ids": folder_ids or None,
            }
            if reg_id:
                kwargs["embedding_model_registry_id"] = reg_id
            elif prov_id and model_name:
                kwargs["embedding_provider_id"] = prov_id
                kwargs["embedding_model_name"] = model_name
            else:
                return "Knowledge base has no embedding configuration."

            svc = RetrievalService()
            result = await svc.retrieve(**kwargs)

        if not result.results:
            return "No relevant passages found."

        chunks = [
            {"content": r.content, "title": r.title, "score": r.score}
            for r in result.results
        ]
        return format_context_chunks(chunks, max_tokens=3000)

    return knowledge_search
