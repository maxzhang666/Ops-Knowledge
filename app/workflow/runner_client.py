"""HTTP client for the Docker-based Python Runner service.

Imported by plan 18 Code Node and (later) Agent `code_execute` tool. Inside
the compose network the Runner is reachable by service name. For local dev
against a manually-started runner, override via `RUNNER_URL` env var.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

RUNNER_URL = os.getenv("RUNNER_URL", "http://runner-python:9100")
DEFAULT_HTTP_TIMEOUT = 15.0


class RunnerError(RuntimeError):
    pass


class RunnerClient:
    def __init__(
        self,
        base_url: str = RUNNER_URL,
        request_timeout: float = DEFAULT_HTTP_TIMEOUT,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._http_timeout = request_timeout

    async def execute(
        self,
        *,
        code: str,
        inputs: dict[str, Any] | None = None,
        timeout: float = 10.0,
        memory_limit: int = 256 * 1024 * 1024,
        request_id: str | None = None,
    ) -> dict:
        """Execute `code` remotely. Returns the Runner's ExecuteResponse dict.

        `timeout` is the CODE execution cap enforced by the runner. The HTTP
        timeout is set slightly higher so the runner can surface its own
        timeout/error response rather than us killing the HTTP call first.
        """
        body = {
            "code": code,
            "inputs": inputs or {},
            "timeout": timeout,
            "memory_limit": memory_limit,
            "request_id": request_id,
        }
        http_timeout = max(timeout + 5.0, self._http_timeout)
        async with httpx.AsyncClient(timeout=http_timeout) as cli:
            try:
                r = await cli.post(f"{self._base}/runner/execute", json=body)
            except httpx.HTTPError as e:
                raise RunnerError(f"runner unreachable: {e}") from e
        if r.status_code != 200:
            raise RunnerError(f"runner HTTP {r.status_code}: {r.text[:500]}")
        return r.json()

    async def healthz(self) -> bool:
        async with httpx.AsyncClient(timeout=3.0) as cli:
            try:
                r = await cli.get(f"{self._base}/healthz")
                return r.status_code == 200
            except httpx.HTTPError:
                return False
