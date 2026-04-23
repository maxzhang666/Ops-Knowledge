"""Transport dispatch + auth header translation.

We don't exercise real MCP sessions here (needs a live server) — those
are covered by the integration tests run manually against a reference
server (e.g. ``npx @modelcontextprotocol/server-everything``).
"""
from types import SimpleNamespace

import pytest

from app.mcp.transports.base import build_headers, get_transport, tool_from_mcp
from app.mcp.transports.http import StreamableHTTPTransport
from app.mcp.transports.sse import SSETransport
from app.mcp.transports.stdio import StdioTransport


def test_build_headers_bearer():
    h = build_headers({"bearer_token": "abc"})
    assert h == {"Authorization": "Bearer abc"}


def test_build_headers_api_key_custom():
    h = build_headers({"api_key": "k", "api_key_header": "X-Foo"})
    assert h == {"X-Foo": "k"}


def test_build_headers_api_key_default():
    h = build_headers({"api_key": "k"})
    assert h == {"X-API-Key": "k"}


def test_build_headers_combined():
    h = build_headers({
        "bearer_token": "t",
        "api_key": "k",
        "extra_headers": {"X-Trace": "id"},
    })
    assert h["Authorization"] == "Bearer t"
    assert h["X-API-Key"] == "k"
    assert h["X-Trace"] == "id"


def test_build_headers_empty():
    assert build_headers(None) == {}
    assert build_headers({}) == {}


def test_get_transport_dispatch():
    http_server = SimpleNamespace(
        transport_type="http", config={"url": "https://h/mcp"}, auth_config=None,
    )
    sse_server = SimpleNamespace(
        transport_type="sse", config={"url": "https://s/sse"}, auth_config=None,
    )
    stdio_server = SimpleNamespace(
        transport_type="stdio", config={"command": "c", "args": []}, auth_config=None,
    )
    assert isinstance(get_transport(http_server), StreamableHTTPTransport)
    assert isinstance(get_transport(sse_server), SSETransport)
    assert isinstance(get_transport(stdio_server), StdioTransport)


def test_get_transport_unknown():
    bad = SimpleNamespace(transport_type="quic", config={}, auth_config=None)
    with pytest.raises(ValueError):
        get_transport(bad)


def test_tool_from_mcp_shapes():
    # Upstream SDK uses `inputSchema`; guard against it renaming to snake_case
    upstream = SimpleNamespace(name="add", description="Sum 2 ints", inputSchema={"type": "object"})
    t = tool_from_mcp(upstream)
    assert t.name == "add"
    assert t.description == "Sum 2 ints"
    assert t.input_schema == {"type": "object"}


def test_tool_from_mcp_missing_description():
    upstream = SimpleNamespace(name="x", inputSchema=None)
    t = tool_from_mcp(upstream)
    assert t.description is None
    assert t.input_schema is None
