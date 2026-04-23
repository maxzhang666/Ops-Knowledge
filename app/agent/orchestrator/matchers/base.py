from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class MatchInput:
    """What matchers look at. Orchestrator builds one per incoming message."""
    message: str
    metadata: dict                      # {"trusted": {...}, "input": {...}}
    agent_orchestrator_config: dict     # classifier / trusted paths etc.
    db_factory: Any                     # async session factory for llm_intent


@dataclass
class MatchResult:
    """Outcome of evaluating one rule.

    ``matched=False`` means the rule didn't fire; ``details`` carries
    per-match-type extras (e.g. llm_intent category + confidence) that
    land in the trace regardless of match outcome.
    """
    matched: bool
    details: dict[str, Any]


class Matcher(Protocol):
    async def __call__(self, rule_match_config: dict, input: MatchInput) -> MatchResult: ...
