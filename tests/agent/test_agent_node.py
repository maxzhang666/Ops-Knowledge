"""Unit tests for the ``agent_react`` workflow node.

We can't spin up a real LLM or MCP server in unit tests; this focuses
on the translation layers we own — server → MCPClient dict, auth →
headers, and node registration.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.workflow.nodes._agent_react import (
    _auth_headers,
    _server_to_mcp_client_entry,
)


def _server(**kw):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=kw.get("name", "s"),
        transport_type=kw.get("transport_type", "http"),
        config=kw.get("config", {"url": "https://x/mcp"}),
        auth_config=kw.get("auth_config") or {},
        is_active=True,
    )


def test_http_mapping_plain():
    s = _server(transport_type="http", config={"url": "https://a/mcp"})
    entry = _server_to_mcp_client_entry(s)
    assert entry == {"transport": "streamable_http", "url": "https://a/mcp"}


def test_http_mapping_with_headers_and_bearer():
    s = _server(
        transport_type="http",
        config={"url": "https://a/mcp", "headers": {"X-Tenant": "acme"}},
        auth_config={"bearer_token": "t"},
    )
    entry = _server_to_mcp_client_entry(s)
    assert entry["transport"] == "streamable_http"
    assert entry["headers"]["X-Tenant"] == "acme"
    assert entry["headers"]["Authorization"] == "Bearer t"


def test_sse_mapping():
    s = _server(transport_type="sse", config={"url": "https://a/sse"})
    entry = _server_to_mcp_client_entry(s)
    assert entry["transport"] == "sse"
    assert entry["url"] == "https://a/sse"


def test_stdio_mapping():
    s = _server(
        transport_type="stdio",
        config={"command": "npx", "args": ["-y", "@m/server"], "env": {"K": "V"}},
    )
    entry = _server_to_mcp_client_entry(s)
    assert entry == {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@m/server"],
        "env": {"K": "V"},
    }


def test_stdio_mapping_no_env():
    s = _server(transport_type="stdio", config={"command": "c", "args": []})
    entry = _server_to_mcp_client_entry(s)
    assert "env" not in entry


def test_unknown_transport_returns_none():
    s = _server(transport_type="quic", config={})
    assert _server_to_mcp_client_entry(s) is None


def test_auth_headers_bearer():
    assert _auth_headers({"bearer_token": "t"}) == {"Authorization": "Bearer t"}


def test_auth_headers_api_key_default_header():
    assert _auth_headers({"api_key": "k"}) == {"X-API-Key": "k"}


def test_auth_headers_api_key_custom_header():
    assert _auth_headers({"api_key": "k", "api_key_header": "X-Foo"}) == {"X-Foo": "k"}


def test_auth_headers_extra_merge():
    got = _auth_headers({"bearer_token": "t", "extra_headers": {"X-Trace": "id"}})
    assert got == {"Authorization": "Bearer t", "X-Trace": "id"}


def test_node_registered_in_registry():
    """Workflow editor relies on registry to render the node in the palette."""
    from app.workflow.nodes.registry import load_builtin_nodes, registry

    load_builtin_nodes()
    types = {n.manifest.type for n in registry.list()}
    assert "agent_react" in types
