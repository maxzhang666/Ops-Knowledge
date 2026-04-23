"""HTTP Request node — outbound HTTP calls.

Note: the project-wide GET/POST-only rule applies to OUR API surface, not to
outbound calls to third-party endpoints. Users can call any method needed.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)


class HTTPRequestNode(AbstractNode):
    manifest = NodeManifest(
        type="http-request",
        category="extension",
        name="HTTP Request",
        description="Call an external HTTP endpoint.",
    )
    io = NodeIO(
        outputs={
            "status_code": {"type": "integer"},
            "body": {},
            "headers": {"type": "object"},
        },
    )
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "default": "GET",
                },
                "url": {"type": "string", "format": "uri"},
                "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                "params": {"type": "object"},
                "body": {},
                "timeout": {"type": "number", "minimum": 0.5, "maximum": 60, "default": 15},
            },
            "required": ["url"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if not ctx.config.get("url"):
            raise ValueError("HTTP Request: missing 'url'")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        method = ctx.config.get("method", "GET").upper()
        url = ctx.config["url"]
        headers = ctx.config.get("headers") or {}
        params = ctx.config.get("params") or {}
        body = ctx.config.get("body")
        timeout = float(ctx.config.get("timeout", 15))

        kwargs: dict[str, Any] = {"params": params, "headers": headers}
        if body is not None and method in ("POST", "PUT", "PATCH"):
            if isinstance(body, (dict, list)):
                kwargs["json"] = body
            else:
                kwargs["content"] = str(body)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, **kwargs)

        ctype = resp.headers.get("content-type", "").lower()
        if "application/json" in ctype or "text/json" in ctype:
            try:
                parsed = resp.json()
            except Exception:
                parsed = resp.text
        else:
            parsed = resp.text

        return NodeResult(outputs={
            "status_code": resp.status_code,
            "body": parsed,
            "headers": dict(resp.headers),
        })
