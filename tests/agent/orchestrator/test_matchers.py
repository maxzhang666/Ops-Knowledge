"""4 matchers + condition trust whitelist (B6)."""
import pytest

from app.agent.orchestrator.matchers import (
    MatchInput,
    match_condition,
    match_keyword,
    match_llm_intent,
    match_regex,
)


def _input(message="hello", metadata=None, orch_cfg=None):
    return MatchInput(
        message=message,
        metadata=metadata or {"trusted": {}, "input": {}},
        agent_orchestrator_config=orch_cfg or {},
        db_factory=None,
    )


# ── Keyword ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_keyword_hit_case_insensitive_default():
    r = await match_keyword({"any_of": ["FOO"]}, _input("hello foo world"))
    assert r.matched
    assert r.details["hits"] == ["FOO"]


@pytest.mark.asyncio
async def test_keyword_case_sensitive():
    r = await match_keyword({"any_of": ["FOO"], "case_sensitive": True}, _input("foo"))
    assert not r.matched


@pytest.mark.asyncio
async def test_keyword_miss():
    r = await match_keyword({"any_of": ["xyz"]}, _input("foo bar"))
    assert not r.matched
    assert r.details["hits"] == []


# ── Regex ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_regex_hit():
    r = await match_regex({"pattern": "VPN|远程", "flags": "i"}, _input("My VPN is down"))
    assert r.matched
    assert r.details["match_span"] is not None


@pytest.mark.asyncio
async def test_regex_invalid_pattern_soft_fails():
    """Patterns should be caught by Pydantic, but if something slips
    through to runtime we don't crash routing."""
    r = await match_regex({"pattern": "(unterminated", "flags": ""}, _input("x"))
    assert not r.matched
    assert "error" in r.details


# ── Condition (trust) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_condition_trusted_path_hit():
    r = await match_condition(
        {"path": "user.role", "op": "==", "value": "admin"},
        _input(
            metadata={"trusted": {"user": {"role": "admin"}}, "input": {}},
            orch_cfg={"trusted_metadata_paths": ["user.role"]},
        ),
    )
    assert r.matched


@pytest.mark.asyncio
async def test_condition_untrusted_path_blocked():
    """Even if rule references a non-whitelisted path at runtime (e.g. stale
    rule after whitelist shrinks), matcher returns no-match rather than
    exposing untrusted data."""
    r = await match_condition(
        {"path": "customer_level", "op": "==", "value": "vip"},
        _input(
            metadata={"trusted": {"user": {}}, "input": {"customer_level": "vip"}},
            orch_cfg={"trusted_metadata_paths": ["user.role"]},  # customer_level NOT listed
        ),
    )
    assert not r.matched
    assert r.details["reason"] == "path_not_trusted"


@pytest.mark.asyncio
async def test_condition_in_op():
    r = await match_condition(
        {"path": "user.role", "op": "in", "value": ["admin", "ops"]},
        _input(
            metadata={"trusted": {"user": {"role": "ops"}}, "input": {}},
            orch_cfg={"trusted_metadata_paths": ["user.role"]},
        ),
    )
    assert r.matched


@pytest.mark.asyncio
async def test_condition_none_actual_not_matched():
    r = await match_condition(
        {"path": "user.role", "op": ">", "value": 5},
        _input(
            metadata={"trusted": {"user": {}}, "input": {}},  # role missing
            orch_cfg={"trusted_metadata_paths": ["user.role"]},
        ),
    )
    assert not r.matched


# ── LLM intent ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_intent_uses_classifier_result_cache():
    orch_cfg = {
        "classifier": {"confidence_threshold": 0.6},
        "_classifier_result": {"category": "product_question", "confidence": 0.9},
    }
    r = await match_llm_intent({"category": "product_question"}, _input(orch_cfg=orch_cfg))
    assert r.matched


@pytest.mark.asyncio
async def test_llm_intent_below_threshold_misses():
    orch_cfg = {
        "classifier": {"confidence_threshold": 0.8},
        "_classifier_result": {"category": "product_question", "confidence": 0.5},
    }
    r = await match_llm_intent({"category": "product_question"}, _input(orch_cfg=orch_cfg))
    assert not r.matched


@pytest.mark.asyncio
async def test_llm_intent_wrong_category_misses():
    orch_cfg = {
        "classifier": {"confidence_threshold": 0.5},
        "_classifier_result": {"category": "billing", "confidence": 0.9},
    }
    r = await match_llm_intent({"category": "product_question"}, _input(orch_cfg=orch_cfg))
    assert not r.matched
