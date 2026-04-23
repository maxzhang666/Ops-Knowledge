"""Condition matcher — path-op-value over trusted metadata.

Paths are restricted to ``orchestrator_config.trusted_metadata_paths``
whitelist (spec 04 §Metadata trust). A rule referencing a non-whitelisted
path is rejected at create time; at runtime we still double-check so a
stale rule (e.g. admin removed a path from the whitelist after the rule
was created) can't silently start matching untrusted data.
"""
from __future__ import annotations

from app.agent.orchestrator.matchers.base import MatchInput, MatchResult
from app.agent.orchestrator.metadata import resolve_trusted_path


async def match_condition(rule_match_config: dict, input: MatchInput) -> MatchResult:
    path = rule_match_config["path"]
    op = rule_match_config["op"]
    expected = rule_match_config["value"]

    whitelist = input.agent_orchestrator_config.get("trusted_metadata_paths") or []
    if path not in whitelist:
        # Stale rule referencing a now-untrusted path → treat as no-match
        # rather than raise. Admin sees this in trace detail.
        return MatchResult(matched=False, details={"reason": "path_not_trusted", "path": path})

    actual = resolve_trusted_path(input.metadata, path)
    try:
        matched = _apply_op(actual, op, expected)
    except TypeError:
        # e.g. comparing None to a number — treat as no-match, not a crash
        matched = False

    return MatchResult(
        matched=matched,
        details={"path": path, "op": op, "actual": actual, "expected": expected},
    )


def _apply_op(actual, op: str, expected):
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == ">":
        return actual is not None and actual > expected
    if op == "<":
        return actual is not None and actual < expected
    if op == ">=":
        return actual is not None and actual >= expected
    if op == "<=":
        return actual is not None and actual <= expected
    raise ValueError(f"unknown op: {op}")
