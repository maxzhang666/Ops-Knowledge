"""Engine cascade — priority order + tried_rules + lazy classifier."""
import uuid
from types import SimpleNamespace

import pytest

from app.agent.orchestrator import engine
from app.agent.orchestrator.matchers.base import MatchInput


def _rule(priority, match_type, match_config, id_=None):
    return SimpleNamespace(
        id=id_ or uuid.uuid4(),
        agent_id=uuid.uuid4(),
        priority=priority,
        is_active=True,
        match_type=match_type,
        match_config=match_config,
        handler_type="simple_agent",
        handler_id=uuid.uuid4(),
        handler_config={},
        on_handler_error="use_default",
    )


def _input(msg="hello", orch_cfg=None):
    return MatchInput(
        message=msg,
        metadata={"trusted": {"user": {"role": "user"}}, "input": {}},
        agent_orchestrator_config=orch_cfg or {"trusted_metadata_paths": ["user.role"]},
        db_factory=None,
    )


@pytest.mark.asyncio
async def test_first_match_wins_respecting_priority():
    r1 = _rule(1.0, "keyword", {"any_of": ["zzz"]})           # miss
    r2 = _rule(2.0, "keyword", {"any_of": ["hello"]})         # hit
    r3 = _rule(3.0, "keyword", {"any_of": ["hello", "xyz"]})  # would hit but lower priority
    decision = await engine.evaluate([r1, r2, r3], _input("hello world"))
    assert decision.matched_rule is r2
    assert decision.tried_rule_ids == [str(r1.id), str(r2.id)]


@pytest.mark.asyncio
async def test_no_match_returns_default_signal():
    r1 = _rule(1.0, "keyword", {"any_of": ["zzz"]})
    decision = await engine.evaluate([r1], _input("hello world"))
    assert decision.matched_rule is None
    assert decision.match_type_used == "default"
    assert decision.tried_rule_ids == [str(r1.id)]


@pytest.mark.asyncio
async def test_skip_rule_ids_fallback_next_behavior():
    r1 = _rule(1.0, "keyword", {"any_of": ["hello"]})
    r2 = _rule(2.0, "keyword", {"any_of": ["hello"]})
    # Skip r1 as if its handler already failed
    decision = await engine.evaluate([r1, r2], _input("hello"), skip_rule_ids=[str(r1.id)])
    assert decision.matched_rule is r2


@pytest.mark.asyncio
async def test_classifier_not_called_when_zero_cost_wins(monkeypatch):
    """llm_intent rule is present but an earlier keyword rule wins →
    classifier MUST NOT be called (cost saving)."""
    r1 = _rule(1.0, "keyword", {"any_of": ["hello"]})
    r2 = _rule(2.0, "llm_intent", {"category": "product"})

    async def _fail_classify(**_kw):  # pragma: no cover
        raise AssertionError("classifier should not run")

    monkeypatch.setattr("app.agent.orchestrator.engine.classify", _fail_classify)
    decision = await engine.evaluate([r1, r2], _input("hello there"))
    assert decision.matched_rule is r1
    assert decision.classifier_output is None
