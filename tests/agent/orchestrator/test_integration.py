"""Integration: engine + dispatcher + fake adapters + audit hook.

Not end-to-end with real DB — we mock the db_factory + adapter registry
but exercise the full code path: priority ordering → match → dispatch
→ audit call. That's enough to catch wiring regressions (M5).
"""
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.agent.orchestrator import audit, engine
from app.agent.orchestrator.adapters import DispatchContext
from app.agent.orchestrator.events import OrchestratorEvent


class _RecAdapter:
    """Records invocation and yields a minimal content_delta stream."""
    invocations = []

    def __init__(self, handler_type: str = "workflow"):
        self.handler_type = handler_type

    async def dispatch(self, msg, hid, hcfg, ctx):
        _RecAdapter.invocations.append((self.handler_type, hid, msg))
        yield OrchestratorEvent(type="content_delta", data={"delta": f"[{self.handler_type}] {msg}"})


@pytest.fixture
def clean_invocations():
    _RecAdapter.invocations = []
    yield
    _RecAdapter.invocations = []


@pytest.fixture
def patched_env(monkeypatch):
    """Patch get_adapter to return our recorder + stub audit writes."""
    from app.agent.orchestrator import dispatcher as _disp

    def _fake_get_adapter(handler_type):
        return _RecAdapter(handler_type)

    monkeypatch.setattr(_disp, "get_adapter", _fake_get_adapter)

    writes: list[dict] = []

    async def _fake_record_trace(_db_factory, **kw):
        writes.append(kw)

    monkeypatch.setattr(audit, "record_trace", _fake_record_trace)
    return writes


def _rule(priority, match_type, match_config, handler_type="workflow"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        priority=priority,
        is_active=True,
        match_type=match_type,
        match_config=match_config,
        handler_type=handler_type,
        handler_id=uuid.uuid4(),
        handler_config={},
        on_handler_error="use_default",
    )


@pytest.mark.asyncio
async def test_rule_hit_dispatches_and_audits(clean_invocations, patched_env):
    from app.agent.orchestrator.service import OrchestratorService

    rules = [
        _rule(1.0, "keyword", {"any_of": ["zzz"]}),
        _rule(2.0, "keyword", {"any_of": ["hello"]}),
        _rule(3.0, "keyword", {"any_of": ["hello"]}),
    ]

    # Build a fake agent with default handler + whitelist
    agent = SimpleNamespace(
        id=uuid.uuid4(),
        orchestrator_config={
            "default_handler": {"handler_type": "workflow", "handler_id": str(uuid.uuid4())},
            "trusted_metadata_paths": ["user.role"],
        },
    )

    # Stub _active_rules to return our rules
    async def _stub_active(self, agent_id, agent=None):
        return rules

    from app.agent.orchestrator.service import OrchestratorService
    OrchestratorService._active_rules = _stub_active  # type: ignore[attr-defined]

    @asynccontextmanager
    async def _fake_session():
        yield None

    class _FakeDB:
        async def commit(self):
            pass

    svc = OrchestratorService(_FakeDB())

    events = []
    async for ev in svc.route(
        agent=agent,
        user_message="hello world",
        conversation_id=None,
        user_id=uuid.uuid4(),
        user_role="user",
    ):
        events.append(ev)

    # Expected: orchestrator_decision + content_delta + nothing else
    types = [e.type for e in events]
    assert "orchestrator_decision" in types
    assert "content_delta" in types
    # Second rule (priority 2.0) wins
    assert _RecAdapter.invocations[0][0] == "workflow"
    assert "hello world" in _RecAdapter.invocations[0][2]
    # Audit called once with matched_rule_id set
    assert patched_env
    assert patched_env[-1]["matched_rule_id"] == rules[1].id


@pytest.mark.asyncio
async def test_no_match_goes_to_default(clean_invocations, patched_env):
    from app.agent.orchestrator.service import OrchestratorService

    default_hid = uuid.uuid4()
    agent = SimpleNamespace(
        id=uuid.uuid4(),
        orchestrator_config={
            "default_handler": {"handler_type": "workflow", "handler_id": str(default_hid)},
            "trusted_metadata_paths": ["user.role"],
        },
    )

    rules = [_rule(1.0, "keyword", {"any_of": ["nope"]})]

    async def _stub_active(self, agent_id, agent=None):
        return rules

    OrchestratorService._active_rules = _stub_active  # type: ignore[attr-defined]

    class _FakeDB:
        async def commit(self):
            pass

    svc = OrchestratorService(_FakeDB())

    events = [
        ev async for ev in svc.route(
            agent=agent,
            user_message="no match here",
            conversation_id=None,
            user_id=uuid.uuid4(),
            user_role="user",
        )
    ]

    # Audit should record match_type_used='default' + matched_rule_id None
    audit_kw = patched_env[-1]
    assert audit_kw["match_type_used"] == "default"
    assert audit_kw["matched_rule_id"] is None
