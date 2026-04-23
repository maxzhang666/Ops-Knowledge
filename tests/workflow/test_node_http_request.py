import httpx
import pytest

from app.workflow.nodes._http_request import HTTPRequestNode
from app.workflow.nodes.base import NodeContext


def _ctx(**cfg):
    return NodeContext(node_id="h", node_type="http-request", config=cfg)


def _patch_httpx(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def _init(self, *a, **kw):
        kw["transport"] = transport
        orig_init(self, *a, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _init)


@pytest.mark.asyncio
async def test_get_json(monkeypatch):
    def handler(req):
        return httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})
    _patch_httpx(monkeypatch, handler)
    node = HTTPRequestNode()
    res = await node.execute(_ctx(url="https://example.test/a", method="GET"))
    assert res.outputs["status_code"] == 200
    assert res.outputs["body"] == {"ok": True}


@pytest.mark.asyncio
async def test_post_json_body(monkeypatch):
    captured = {}

    def handler(req):
        captured["method"] = req.method
        captured["body"] = req.content.decode()
        return httpx.Response(201, json={"id": 1}, headers={"content-type": "application/json"})

    _patch_httpx(monkeypatch, handler)
    node = HTTPRequestNode()
    res = await node.execute(_ctx(
        url="https://example.test/x", method="POST", body={"name": "a"},
    ))
    assert captured["method"] == "POST"
    assert '"name":"a"' in captured["body"]  # httpx.json= serializes compactly
    assert res.outputs["status_code"] == 201


@pytest.mark.asyncio
async def test_text_response_fallback(monkeypatch):
    def handler(req):
        return httpx.Response(200, text="plain text", headers={"content-type": "text/plain"})
    _patch_httpx(monkeypatch, handler)
    node = HTTPRequestNode()
    res = await node.execute(_ctx(url="https://example.test/t"))
    assert res.outputs["body"] == "plain text"


@pytest.mark.asyncio
async def test_500_returns_status_not_raises(monkeypatch):
    def handler(req):
        return httpx.Response(500, text="boom")
    _patch_httpx(monkeypatch, handler)
    node = HTTPRequestNode()
    res = await node.execute(_ctx(url="https://example.test/z"))
    assert res.outputs["status_code"] == 500
    assert res.outputs["body"] == "boom"


@pytest.mark.asyncio
async def test_validate_requires_url():
    node = HTTPRequestNode()
    with pytest.raises(ValueError, match="missing 'url'"):
        await node.validate(_ctx())
