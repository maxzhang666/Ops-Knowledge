"""Knowledge Retrieval node — wraps 1a RetrievalService.retrieve.

Returns `chunks` array + `is_empty` flag. The is_empty flag lets downstream
If-Else nodes (plan 18) route "no results → fallback" paths.
"""
from __future__ import annotations

from app.core.database import async_session
from app.integration import workflow_to_knowledge as wtok
from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)


class KnowledgeRetrievalNode(AbstractNode):
    manifest = NodeManifest(
        type="knowledge-retrieval",
        category="knowledge",
        name="Knowledge Retrieval",
        description="Hybrid search against one or more knowledge bases.",
    )
    io = NodeIO(
        inputs={"query": {"type": "string"}},
        outputs={
            "chunks": {"type": "array", "items": {"type": "object"}},
            "is_empty": {"type": "boolean"},
        },
    )
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "knowledge_base_ids": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                    "minItems": 1,
                },
                "folder_ids": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
                "top_k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "score_threshold": {"type": "number", "minimum": 0, "default": 0.0},
                "rewrite": {"type": "boolean", "default": False},
            },
            "required": ["knowledge_base_ids"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if not (ctx.config.get("knowledge_base_ids") or []):
            raise ValueError("KnowledgeRetrieval: at least one knowledge_base_id required")
        if "query" not in ctx.inputs:
            raise ValueError("KnowledgeRetrieval: missing 'query' input")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        # Go through the integration facade — never import app.knowledge.*
        # directly from a workflow node. See plan 21.
        async with async_session() as db:
            chunks = await wtok.retrieve(
                db,
                query=str(ctx.inputs["query"]),
                kb_ids=[str(k) for k in ctx.config["knowledge_base_ids"]],
                top_k=int(ctx.config.get("top_k", 10)),
                folder_ids=(
                    [str(f) for f in (ctx.config.get("folder_ids") or [])] or None
                ),
                score_threshold=float(ctx.config.get("score_threshold", 0.0)),
                rewrite=bool(ctx.config.get("rewrite", False)),
            )
        return NodeResult(outputs={"chunks": chunks, "is_empty": len(chunks) == 0})
