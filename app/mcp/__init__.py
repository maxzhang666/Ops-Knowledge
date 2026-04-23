"""MCP Client integration (Plan 30).

System acts as an MCP Client; MCP Servers are a system-level resource.
The official ``mcp`` SDK owns the wire protocol — this package adds a
thin transport-agnostic facade, CRUD service, and router on top.
"""
