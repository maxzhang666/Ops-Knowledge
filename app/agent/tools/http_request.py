"""http_request — calls external HTTP APIs.

Guardrails: timeout cap, body-size cap on response, no host allowlist
enforcement yet (admin-level control deferred to Plan 30 M3 audit pass).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from langchain_core.tools import BaseTool, tool

if TYPE_CHECKING:
    from app.agent.tools import ToolContext


RESPONSE_CAP = 8_000  # chars — what we hand back to the LLM
REQUEST_TIMEOUT = 15.0


def make_http_request(ctx: "ToolContext") -> BaseTool:  # noqa: ARG001
    """ctx unused; the tool is stateless w.r.t. request scope."""

    @tool
    async def http_request(
        method: str,
        url: str,
        headers: dict | None = None,
        body: str | None = None,
    ) -> str:
        """Make an HTTP request to an external API.

        ``method`` is GET/POST/PUT/DELETE (case-insensitive).
        ``body`` is sent as the raw request body (set ``Content-Type``
        in ``headers`` to indicate format).

        Returns a string: "<status> <reason>\\n<first 8KB of response body>".
        Network errors return "[error] ...".
        """
        m = (method or "GET").upper()
        if m not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
            return f"[error] unsupported method: {m}"
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.request(m, url, headers=headers or None, content=body)
        except httpx.TimeoutException:
            return "[error] request timed out"
        except Exception as e:  # noqa: BLE001
            return f"[error] {str(e)[:300]}"

        text = resp.text[:RESPONSE_CAP]
        truncated = "" if len(resp.text) <= RESPONSE_CAP else "\n[truncated]"
        return f"{resp.status_code} {resp.reason_phrase}\n{text}{truncated}"

    return http_request
