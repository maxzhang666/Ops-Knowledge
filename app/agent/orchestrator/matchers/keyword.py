from __future__ import annotations

from app.agent.orchestrator.matchers.base import MatchInput, MatchResult


async def match_keyword(rule_match_config: dict, input: MatchInput) -> MatchResult:
    keywords: list[str] = rule_match_config.get("any_of") or []
    case_sensitive: bool = bool(rule_match_config.get("case_sensitive"))
    haystack = input.message if case_sensitive else input.message.casefold()

    hits: list[str] = []
    for kw in keywords:
        probe = kw if case_sensitive else kw.casefold()
        if probe and probe in haystack:
            hits.append(kw)

    return MatchResult(matched=bool(hits), details={"hits": hits})
