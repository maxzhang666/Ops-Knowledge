"""Parameter Extractor — LLM-backed structured extraction from free text."""
from __future__ import annotations

import json
import uuid
from typing import Any

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


class ParameterExtractorNode(AbstractNode):
    manifest = NodeManifest(
        type="parameter-extractor",
        category="llm",
        name="Parameter Extractor",
        description="Extract structured parameters from free text via LLM.",
    )
    io = NodeIO(inputs={"text": {"type": "string"}})
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "model_provider_id": {"type": "string", "format": "uuid"},
                "model_name": {"type": "string"},
                "parameters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string", "enum": ["string", "number", "boolean", "array"]},
                            "description": {"type": "string"},
                            "required": {"type": "boolean", "default": False},
                        },
                        "required": ["name", "type"],
                    },
                    "minItems": 1,
                },
                "instruction": {"type": "string"},
            },
            "required": ["model_provider_id", "model_name", "parameters"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if "text" not in ctx.inputs:
            raise ValueError("Parameter Extractor: missing 'text' input")
        for key in ("model_provider_id", "model_name", "parameters"):
            if not ctx.config.get(key):
                raise ValueError(f"Parameter Extractor: missing '{key}'")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        text = str(ctx.inputs["text"])
        params = ctx.config["parameters"]
        schema_desc = "\n".join(
            f"- {p['name']} ({p['type']}){' [required]' if p.get('required') else ''}"
            + (f": {p.get('description','')}" if p.get("description") else "")
            for p in params
        )
        instruction = ctx.config.get("instruction", "Extract the parameters below.")
        system = (
            f"{instruction} Respond with ONLY a JSON object mapping parameter names "
            "to extracted values. Missing optional values become null. No prose."
        )
        user = f"Parameters:\n{schema_desc}\n\nInput text:\n{text}"

        pid = uuid.UUID(str(ctx.config["model_provider_id"]))
        model = ctx.config["model_name"]
        async with async_session() as db:
            svc = ModelService(db)
            resp = await svc.chat(
                pid, model,
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.0,
                max_tokens=512,
                trace_id=ctx.trace_id,
            )
        content = resp["choices"][0]["message"]["content"]
        parsed = _parse_json(content)

        missing = [
            p["name"] for p in params
            if p.get("required") and (
                p["name"] not in parsed or parsed[p["name"]] in (None, "")
            )
        ]
        if missing:
            raise RuntimeError(f"Parameter Extractor: missing required fields: {missing}")
        coerced = {p["name"]: _coerce(parsed.get(p["name"]), p["type"]) for p in params}
        return NodeResult(outputs=coerced)


def _parse_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    raise RuntimeError(f"Parameter Extractor: invalid JSON output: {raw[:200]!r}")


def _coerce(value: Any, declared: str) -> Any:
    if value is None:
        return None
    try:
        if declared == "string":
            return str(value)
        if declared == "number":
            if isinstance(value, bool):
                return value  # bool is a subtype of int — don't flatten
            s = str(value)
            return float(s) if "." in s else int(value)
        if declared == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")
        if declared == "array":
            return value if isinstance(value, list) else [value]
    except (ValueError, TypeError):
        pass
    return value
