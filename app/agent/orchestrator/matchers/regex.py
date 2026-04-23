from __future__ import annotations

import re

from app.agent.orchestrator.matchers.base import MatchInput, MatchResult
from app.agent.orchestrator.schemas import _flags_to_re


async def match_regex(rule_match_config: dict, input: MatchInput) -> MatchResult:
    pattern: str = rule_match_config["pattern"]
    flags_str: str = rule_match_config.get("flags") or ""
    try:
        pat = re.compile(pattern, _flags_to_re(flags_str))
    except re.error as e:
        # Pydantic validated at save time; if we see an invalid regex here
        # it means the rule was tampered with directly in DB. Don't crash
        # routing — skip with a debug detail.
        return MatchResult(matched=False, details={"error": f"invalid regex: {e}"})

    match = pat.search(input.message)
    return MatchResult(
        matched=match is not None,
        details={"match_span": match.span() if match else None},
    )
