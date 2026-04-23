"""SSO unit tests are pure-Python — skip root setup_db DB autouse."""
import pytest


@pytest.fixture(autouse=True)
def setup_db():
    yield
