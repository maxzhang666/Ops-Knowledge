"""Override the root-level ``setup_db`` autouse fixture — MCP unit tests
stub the transport + DB entirely and don't need a real Postgres."""
import pytest


@pytest.fixture(autouse=True)
def setup_db():
    yield
