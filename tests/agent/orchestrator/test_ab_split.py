"""A/B stable split (Plan 31 N3.3)."""
import uuid

from app.agent.orchestrator.service import _ab_group_for


def test_same_user_same_agent_stable():
    user = uuid.uuid4()
    agent = uuid.uuid4()
    first = _ab_group_for(user, agent)
    for _ in range(100):
        assert _ab_group_for(user, agent) == first


def test_different_agents_split_independently():
    """Same user on two different Agents might fall in different groups.
    The hash should not be user-only — otherwise an A-group user is always
    A everywhere, which defeats per-agent experiments."""
    user = uuid.uuid4()
    got_both = False
    buckets = set()
    for _ in range(40):
        buckets.add(_ab_group_for(user, uuid.uuid4()))
        if {"A", "B"}.issubset(buckets):
            got_both = True
            break
    assert got_both, "Hash should split across agents, got only one bucket"


def test_none_user_returns_none():
    assert _ab_group_for(None, uuid.uuid4()) is None


def test_both_values_observed_across_users():
    """Hash uniformity smoke — 200 random users hash to both A and B."""
    agent = uuid.uuid4()
    groups = {_ab_group_for(uuid.uuid4(), agent) for _ in range(200)}
    assert "A" in groups
    assert "B" in groups
