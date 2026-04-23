"""Verify plan 23 Task 5 wiring: importing bus_relay registers handlers."""
import pytest

from app.integration import event_bus
from app.integration.events import Event


@pytest.fixture(autouse=True)
def _reset():
    event_bus.clear_handlers()
    yield
    event_bus.clear_handlers()


@pytest.mark.asyncio
async def test_bus_relay_registers_all_event_names():
    # Import triggers @on() decorator side-effects.
    import app.observability.bus_relay  # noqa: F401

    # At least one handler should be registered for each known event.
    for name in (
        "document.completed", "document.failed",
        "kb.reindex_completed",
        "workflow.execution_completed", "workflow.execution_failed",
        "governance.alert",
    ):
        handlers = event_bus.registered_handlers(name)
        assert handlers, f"no handler registered for {name}"


@pytest.mark.asyncio
async def test_relay_swallows_langfuse_failure(monkeypatch):
    """Relay must not raise even if the Langfuse client blows up — bus
    delivery is best-effort and handler errors can't take down the scheduler."""
    import app.observability.bus_relay  # noqa: F401

    class _Boom:
        def trace(self, *a, **kw): raise RuntimeError("boom")
        def flush(self): pass

    monkeypatch.setattr("app.observability.bus_relay.get_client", lambda: _Boom())

    # Must not raise — if this throws the scheduler's bus subscriber dies.
    await event_bus.dispatch(Event(name="document.completed", source="knowledge"))
