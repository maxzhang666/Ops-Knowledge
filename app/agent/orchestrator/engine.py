"""Rule matching engine — 3-step cascade.

Walks rules in priority order, evaluating each matcher. Classifier is
LAZY: we only pay the LLM cost if a zero-cost rule (condition / keyword
/ regex) hasn't already won AND at least one rule with
``match_type='llm_intent'`` exists in the remaining evaluation set.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.agent.orchestrator.matchers import (
    MatchInput,
    match_condition,
    match_keyword,
    match_llm_intent,
    match_regex,
)
from app.agent.orchestrator.matchers.llm_intent import classify
from app.agent.orchestrator.models import AgentRule

MATCHERS = {
    "condition": match_condition,
    "keyword": match_keyword,
    "regex": match_regex,
    "llm_intent": match_llm_intent,
}


@dataclass
class EngineDecision:
    matched_rule: AgentRule | None  # None ⇒ default handler
    match_type_used: str            # 'default' when no rule matched
    match_latency_ms: int
    tried_rule_ids: list[str]
    classifier_output: dict | None  # {category, confidence, cached} or None


async def evaluate(
    rules: list[AgentRule],
    msg_input: MatchInput,
    skip_rule_ids: list[str] | None = None,
) -> EngineDecision:
    """Iterate ``rules`` (already priority-sorted ascending) and return
    the first match. ``skip_rule_ids`` is used on ``fallback_next`` —
    skip the rule that already failed.
    """
    skip = set(skip_rule_ids or [])
    tried: list[str] = []
    classifier_output: dict | None = None

    t0 = time.monotonic()

    # Lazy-classify optimization: if any llm_intent rule exists AND no
    # earlier rule wins, the first llm_intent evaluation triggers classify()
    # and caches the output into msg_input.agent_orchestrator_config for
    # subsequent llm_intent rules in the same cascade.
    for rule in rules:
        if str(rule.id) in skip or not rule.is_active:
            continue
        tried.append(str(rule.id))

        matcher = MATCHERS.get(rule.match_type)
        if matcher is None:
            continue  # unknown match_type — don't crash, just skip

        if rule.match_type == "llm_intent" and classifier_output is None:
            classifier_cfg = (msg_input.agent_orchestrator_config or {}).get("classifier")
            if classifier_cfg:
                out = await classify(
                    agent_id=_agent_id_of(rule),
                    message=msg_input.message,
                    classifier_cfg=classifier_cfg,
                    db_factory=msg_input.db_factory,
                )
                if out is not None:
                    classifier_output = {
                        "category": out.category,
                        "confidence": out.confidence,
                        "cached": out.cached,
                    }
                    # Mutate config in-place so llm_intent matcher can read it
                    msg_input.agent_orchestrator_config["_classifier_result"] = classifier_output

        result = await matcher(rule.match_config, msg_input)
        if result.matched:
            latency = int((time.monotonic() - t0) * 1000)
            return EngineDecision(
                matched_rule=rule,
                match_type_used=rule.match_type,
                match_latency_ms=latency,
                tried_rule_ids=tried,
                classifier_output=classifier_output,
            )

    latency = int((time.monotonic() - t0) * 1000)
    return EngineDecision(
        matched_rule=None,
        match_type_used="default",
        match_latency_ms=latency,
        tried_rule_ids=tried,
        classifier_output=classifier_output,
    )


def _agent_id_of(rule: AgentRule):
    # Tiny helper for readability; keeps classify()'s call site clean
    return rule.agent_id
