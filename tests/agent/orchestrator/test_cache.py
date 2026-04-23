"""In-memory rules cache — invalidation semantics (Plan 31 N3.4)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.agent.orchestrator import cache


@pytest.fixture(autouse=True)
def _clear():
    cache.clear_all()
    yield
    cache.clear_all()


def _ts(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def test_put_and_get():
    aid = uuid.uuid4()
    t = _ts()
    cache.put_cached_rules(aid, t, ["r1", "r2"])
    assert cache.get_cached_rules(aid, t) == ["r1", "r2"]


def test_updated_at_mismatch_invalidates():
    aid = uuid.uuid4()
    cache.put_cached_rules(aid, _ts(0), ["old"])
    assert cache.get_cached_rules(aid, _ts(10)) is None
    # Subsequent get at original ts also misses — mismatch evicted entry
    assert cache.get_cached_rules(aid, _ts(0)) is None


def test_explicit_invalidate():
    aid = uuid.uuid4()
    t = _ts()
    cache.put_cached_rules(aid, t, ["r"])
    cache.invalidate(aid)
    assert cache.get_cached_rules(aid, t) is None


def test_none_updated_at_never_caches_or_hits():
    aid = uuid.uuid4()
    cache.put_cached_rules(aid, None, ["r"])  # no-op
    assert cache.get_cached_rules(aid, None) is None


def test_returns_shallow_copy():
    """Mutating the returned list should not affect the cache."""
    aid = uuid.uuid4()
    t = _ts()
    cache.put_cached_rules(aid, t, ["a", "b"])
    got = cache.get_cached_rules(aid, t)
    assert got is not None
    got.append("c")
    again = cache.get_cached_rules(aid, t)
    assert again == ["a", "b"]


def test_max_agents_eviction():
    """At the cap, adding one more agent evicts the oldest."""
    import app.agent.orchestrator.cache as c_mod
    original = c_mod._MAX_AGENTS_CACHED
    c_mod._MAX_AGENTS_CACHED = 3
    # Fixed timestamp so put/get compare equal (not wall-clock)
    t = _ts(0)
    try:
        ids = [uuid.uuid4() for _ in range(3)]
        for aid in ids:
            cache.put_cached_rules(aid, t, [])
        # Add a 4th — first one evicted
        new_id = uuid.uuid4()
        cache.put_cached_rules(new_id, t, [])
        assert cache.get_cached_rules(ids[0], t) is None  # FIFO eviction
        assert cache.get_cached_rules(new_id, t) == []
    finally:
        c_mod._MAX_AGENTS_CACHED = original
