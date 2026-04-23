"""Integration tests are pure-Python (no DB). Disable the root setup_db autouse."""
import pytest


@pytest.fixture(autouse=True)
def setup_db():
    yield
