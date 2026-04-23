from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from sandbox import ResourceExhausted, RunnerTimeout, run_python_code

app = FastAPI(title="Ops-Knowledge Runner (Python)", version="1.0")


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=50_000)
    inputs: dict[str, Any] = Field(default_factory=dict)
    timeout: float = Field(10.0, gt=0, le=60)
    memory_limit: int = Field(256 * 1024 * 1024, gt=0, le=1024 * 1024 * 1024)
    request_id: str | None = None


class ExecuteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    ok: bool
    outputs: dict[str, Any] | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    duration_ms: int


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/runner/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest) -> ExecuteResponse:
    rid = req.request_id or uuid.uuid4().hex
    t0 = time.monotonic()
    try:
        res = run_python_code(
            code=req.code, inputs=req.inputs,
            timeout=req.timeout, memory_limit=req.memory_limit,
        )
        return ExecuteResponse(
            request_id=rid, ok=True, outputs=res.outputs,
            stdout=res.stdout, stderr=res.stderr,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    except RunnerTimeout as e:
        return ExecuteResponse(
            request_id=rid, ok=False, error=f"timeout: {e}",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    except ResourceExhausted as e:
        return ExecuteResponse(
            request_id=rid, ok=False, error=f"resource_exhausted: {e}",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as e:  # noqa: BLE001
        return ExecuteResponse(
            request_id=rid, ok=False, error=f"runner_error: {e}",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
