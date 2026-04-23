"""Question Classifier — LLM-backed categorical router.

Emits `branch=<category_id>` so downstream edges activate by sourceHandle
without needing an intermediate If-Else node.
"""
from __future__ import annotations

import json
import uuid

from app.core.database import async_session
from app.model.service import ModelService
from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)


class QuestionClassifierNode(AbstractNode):
    manifest = NodeManifest(
        type="question-classifier",
        category="llm",
        name="Question Classifier",
        description="Classify a query into one of several categories via LLM.",
    )
    io = NodeIO(
        inputs={"query": {"type": "string"}},
        outputs={
            "category_id": {"type": "string"},
            "category_name": {"type": "string"},
        },
    )
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "model_provider_id": {"type": "string", "format": "uuid"},
                "model_name": {"type": "string"},
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["id", "name"],
                    },
                    "minItems": 2,
                },
            },
            "required": ["model_provider_id", "model_name", "categories"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        for key in ("model_provider_id", "model_name", "categories"):
            if not ctx.config.get(key):
                raise ValueError(f"Question Classifier: missing '{key}'")
        if "query" not in ctx.inputs:
            raise ValueError("Question Classifier: missing 'query' input")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        query = str(ctx.inputs["query"])
        categories = ctx.config["categories"]
        cats_text = "\n".join(
            f"- {c['id']}: {c['name']}"
            + (f" — {c.get('description','')}" if c.get("description") else "")
            for c in categories
        )
        system = (
            "You classify user queries into exactly one category. Respond with ONLY "
            "a JSON object: {\"category_id\": \"<id>\"}. No prose, no markdown fence."
        )
        user = f"Categories:\n{cats_text}\n\nQuery: {query}"

        pid = uuid.UUID(str(ctx.config["model_provider_id"]))
        model = ctx.config["model_name"]
        async with async_session() as db:
            svc = ModelService(db)
            resp = await svc.chat(
                pid, model,
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.0,
                max_tokens=64,
                trace_id=ctx.trace_id,
            )
        content = resp["choices"][0]["message"]["content"]
        cat_id = _parse_category_id(content, [c["id"] for c in categories])
        cat_name = next((c["name"] for c in categories if c["id"] == cat_id), cat_id)
        return NodeResult(
            outputs={"category_id": cat_id, "category_name": cat_name},
            branch=cat_id,
        )


def _parse_category_id(raw: str, valid_ids: list[str]) -> str:
    cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        obj = json.loads(cleaned)
        cid = obj.get("category_id")
        if cid in valid_ids:
            return cid
    except Exception:
        pass
    # Defensive substring fallback — LLMs sometimes leak minor fence leftovers.
    for cid in valid_ids:
        if cid in raw:
            return cid
    raise RuntimeError(f"Classifier output did not match any category: {raw[:200]!r}")
