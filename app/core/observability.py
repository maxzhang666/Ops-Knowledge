"""Langfuse client singleton with no-op fallback.

Fail-soft: missing credentials OR SDK import failure → every public call is a
no-op. Lets us instrument everywhere without conditional branches at callsites.

Env vars (3-bootstrap pattern per spec 11):
  LANGFUSE_HOST
  LANGFUSE_PUBLIC_KEY
  LANGFUSE_SECRET_KEY
  LANGFUSE_CAPTURE_IO (optional, "true" to emit raw prompts/outputs — off by default
    because prompts / chunk contents can be sensitive)
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_client = None


def capture_io_enabled() -> bool:
    return os.getenv("LANGFUSE_CAPTURE_IO", "false").lower() == "true"


class _NoopSpan:
    id = None

    def span(self, *a, **kw): return _NoopSpan()
    def generation(self, *a, **kw): return _NoopSpan()
    def update(self, **kw): return None
    def end(self, **kw): return None


class _NoopClient:
    def trace(self, *a, **kw): return _NoopSpan()
    def flush(self): return None


def get_client():
    global _client
    if _client is not None:
        return _client
    host = os.getenv("LANGFUSE_HOST")
    pub = os.getenv("LANGFUSE_PUBLIC_KEY")
    sec = os.getenv("LANGFUSE_SECRET_KEY")
    if not (host and pub and sec):
        log.info("Langfuse not configured — using no-op client")
        _client = _NoopClient()
        return _client
    try:
        from langfuse import Langfuse  # type: ignore
        _client = Langfuse(host=host, public_key=pub, secret_key=sec)
        log.info("Langfuse client initialized host=%s", host)
    except Exception as e:  # noqa: BLE001
        log.warning("Langfuse import/init failed: %s — using no-op", e)
        _client = _NoopClient()
    return _client


def flush() -> None:
    try:
        get_client().flush()
    except Exception:  # noqa: BLE001
        pass


def reset_for_tests() -> None:
    """Test hook — drops the cached client so env changes take effect."""
    global _client
    _client = None
