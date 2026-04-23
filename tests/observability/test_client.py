import os

import pytest

from app.core import observability


@pytest.fixture(autouse=True)
def _reset():
    observability.reset_for_tests()
    yield
    observability.reset_for_tests()


def test_noop_without_credentials(monkeypatch):
    for k in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    client = observability.get_client()
    # Every call chain is a silent no-op
    trace = client.trace(name="t")
    span = trace.span(name="s")
    gen = trace.generation(name="g")
    span.update(output={"x": 1})
    gen.update(output={"y": 2})
    span.end()
    gen.end(usage={"input_tokens": 5, "output_tokens": 10})
    trace.update(output="done")
    client.flush()


def test_capture_io_default_off(monkeypatch):
    monkeypatch.delenv("LANGFUSE_CAPTURE_IO", raising=False)
    assert observability.capture_io_enabled() is False


def test_capture_io_on(monkeypatch):
    monkeypatch.setenv("LANGFUSE_CAPTURE_IO", "true")
    assert observability.capture_io_enabled() is True


def test_flush_never_raises(monkeypatch):
    observability.flush()  # no client initialized yet
    client = observability.get_client()  # noop
    client.flush()
    observability.flush()
