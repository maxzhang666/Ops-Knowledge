import httpx
import pytest

from app.workflow.runner_client import RunnerClient, RunnerError


@pytest.mark.asyncio
async def test_execute_returns_payload():
    async def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/runner/execute"
        payload = await _read_json(req)
        return httpx.Response(
            200,
            json={
                "request_id": payload.get("request_id") or "x",
                "ok": True,
                "outputs": {"y": payload["inputs"]["x"] * 2},
                "stdout": "",
                "stderr": "",
                "error": None,
                "duration_ms": 5,
            },
        )

    client = RunnerClient()
    client._http_timeout = 3.0  # fast for test
    transport = httpx.MockTransport(handler)
    # Monkey-patch AsyncClient via context manager to use our transport.
    orig = httpx.AsyncClient.__init__

    def _patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        orig(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = _patched_init
    try:
        res = await client.execute(code="pass", inputs={"x": 3}, timeout=1)
    finally:
        httpx.AsyncClient.__init__ = orig
    assert res["ok"] is True
    assert res["outputs"] == {"y": 6}


@pytest.mark.asyncio
async def test_non_200_raises():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = RunnerClient()
    client._http_timeout = 3.0
    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient.__init__

    def _patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        orig(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = _patched_init
    try:
        with pytest.raises(RunnerError, match="runner HTTP 500"):
            await client.execute(code="pass", inputs={}, timeout=1)
    finally:
        httpx.AsyncClient.__init__ = orig


async def _read_json(req: httpx.Request) -> dict:
    import json
    return json.loads(req.content.decode())
