"""Workflow-local test config.

DSL / context are pure-Python unit tests — no DB needed. Override the autouse
`setup_db` fixture from the root conftest so these can run without Postgres.

Service / router tests that DO need DB declare `db_session` explicitly.
"""
import pytest


@pytest.fixture(autouse=True)
def setup_db():
    # No-op — skip the DB creation in root conftest for workflow unit tests.
    yield
