"""Ensure the node registry is populated before tests run.

The app's lifespan hook normally calls ``load_builtin_nodes()`` at startup;
pytest bypasses that, so selector lookups (``registry.get("answer")``)
fail with ``Unknown node type`` without this fixture.
"""
from __future__ import annotations

import pytest

from app.workflow.nodes.registry import load_builtin_nodes, registry


@pytest.fixture(scope="session", autouse=True)
def _ensure_nodes_loaded() -> None:
    if not registry.list():
        load_builtin_nodes()
