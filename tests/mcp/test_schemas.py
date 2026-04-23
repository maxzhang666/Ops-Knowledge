"""Transport-config cross-validation — the router relies on these 422s
to reject malformed payloads before they reach ``service.py``.
"""
import pytest
from pydantic import ValidationError

from app.mcp.schemas import MCPServerCreate, MCPServerUpdate


def test_http_config_ok():
    m = MCPServerCreate(
        name="X", transport_type="http",
        config={"url": "https://example.com/mcp", "headers": {"A": "b"}},
    )
    assert m.config["url"] == "https://example.com/mcp"
    assert m.config["headers"] == {"A": "b"}


def test_stdio_config_normalizes():
    m = MCPServerCreate(
        name="X", transport_type="stdio",
        config={"command": "npx", "args": ["-y", "@m/server"], "env": {"K": "V"}},
    )
    assert m.config["command"] == "npx"
    assert m.config["args"] == ["-y", "@m/server"]


def test_http_missing_url_rejected():
    with pytest.raises(ValidationError):
        MCPServerCreate(name="X", transport_type="http", config={})


def test_stdio_missing_command_rejected():
    with pytest.raises(ValidationError):
        MCPServerCreate(name="X", transport_type="stdio", config={"args": []})


def test_transport_config_mismatch_rejected():
    # http config shape doesn't match stdio
    with pytest.raises(ValidationError):
        MCPServerCreate(
            name="X", transport_type="stdio",
            config={"url": "https://foo/mcp"},
        )


def test_update_transport_change_requires_config():
    with pytest.raises(ValidationError):
        MCPServerUpdate(transport_type="stdio")


def test_update_forbid_unknown_keys():
    with pytest.raises(ValidationError):
        MCPServerUpdate(bogus="x")


def test_update_partial_ok():
    u = MCPServerUpdate(name="newname", is_active=False)
    assert u.name == "newname"
    assert u.is_active is False
    assert u.model_dump(exclude_unset=True) == {"name": "newname", "is_active": False}
