"""Cost service unit tests bypass root setup_db (no DB needed)."""
import pytest


@pytest.fixture(autouse=True)
def setup_db():
    yield
