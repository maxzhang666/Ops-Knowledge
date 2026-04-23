"""Tests in this directory stub transports/DB at the unit level.

Override the root ``setup_db`` autouse so pytest doesn't try to create
tables in a non-existent ``ops_knowledge_test`` DB (the existing
``test_agent_crud.py`` already fails without real DB — development
convention, see memory).
"""
import pytest


@pytest.fixture(autouse=True)
def setup_db():
    yield
