"""MCP transport facade.

Each transport wraps the official ``mcp`` SDK client and exposes a
minimal lifecycle (``connect`` / ``list_tools`` / ``call_tool`` /
``close``) so the service layer doesn't care which wire protocol it's
talking to.
"""
from app.mcp.transports.base import MCPTransport, get_transport

__all__ = ["MCPTransport", "get_transport"]
