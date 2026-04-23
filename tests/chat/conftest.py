"""Workflow-pipeline unit tests use heavy patching and don't need DB."""
import pytest


@pytest.fixture(autouse=True)
def setup_db():
    yield
