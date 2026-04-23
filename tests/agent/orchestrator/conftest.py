"""Orchestrator unit tests stub Redis / LLM / DB; skip root setup_db."""
import pytest


@pytest.fixture(autouse=True)
def setup_db():
    yield
