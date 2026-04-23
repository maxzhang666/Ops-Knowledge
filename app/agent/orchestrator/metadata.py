"""Metadata trust-namespace assembly and path resolution.

Incoming chat requests carry a metadata blob from the caller. Condition
rules must never naively match on caller-supplied fields — spec 04
§Metadata trust. The ``route()`` entry point builds a namespaced view:

    {
      "trusted": {"user": {"id": ..., "role": ..., "department_id": ...}},
      "input":   {<caller-supplied>},
    }

Condition matchers may only read paths in ``trusted_metadata_paths``
whitelist (default ``user.role``, ``user.department_id``, ``user.id``).
"""
from __future__ import annotations

import uuid
from typing import Any


def build_metadata(
    *,
    user_id: uuid.UUID,
    user_role: str,
    user_department_id: uuid.UUID | None,
    caller_metadata: dict | None,
) -> dict:
    """Compose the trusted + input namespaces for a single route invocation.

    ``caller_metadata`` is the untrusted blob from the chat request body.
    It's stored under ``input.*`` so it can still appear in traces /
    diagnostics, but never matches condition rules by path.
    """
    return {
        "trusted": {
            "user": {
                "id": str(user_id),
                "role": user_role,
                "department_id": str(user_department_id) if user_department_id else None,
            },
        },
        "input": dict(caller_metadata or {}),
    }


def resolve_trusted_path(metadata: dict, path: str) -> Any:
    """Resolve ``user.role`` → ``metadata.trusted.user.role``.

    Returns ``None`` if any segment is missing (callers treat missing as
    a condition false rather than raising, so a bad rule doesn't crash
    routing for everyone).
    """
    cur: Any = metadata.get("trusted", {})
    for seg in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(seg)
        if cur is None:
            return None
    return cur


def assert_path_trusted(path: str, whitelist: list[str]) -> None:
    """Raise ValueError if ``path`` isn't in the Agent's trust whitelist.

    Called at rule-create / update time so operators can't slip in a
    condition like ``input.customer_level == 'vip'`` that bypasses
    auth. Also called defensively at runtime inside ConditionMatcher.
    """
    if path not in whitelist:
        raise ValueError(
            f"metadata path '{path}' is not in trusted_metadata_paths whitelist"
            f" (allowed: {sorted(whitelist)})"
        )
