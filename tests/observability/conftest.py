import pytest


@pytest.fixture(autouse=True)
def setup_db():
    yield
