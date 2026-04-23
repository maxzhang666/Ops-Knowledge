import pytest

from app.integration import event_bus
from app.integration.events import Event


@pytest.fixture(autouse=True)
def _reset():
    event_bus.clear_handlers()
    yield
    event_bus.clear_handlers()


@pytest.mark.asyncio
async def test_handler_registered_and_dispatched():
    seen: list[Event] = []

    @event_bus.on("document.completed")
    async def _h(ev: Event) -> None:
        seen.append(ev)

    await event_bus.dispatch(Event(name="document.completed", source="test", data={"x": 1}))
    assert len(seen) == 1
    assert seen[0].data == {"x": 1}


@pytest.mark.asyncio
async def test_unrelated_handler_not_invoked():
    seen: list[Event] = []

    @event_bus.on("workflow.execution_completed")
    async def _h(ev: Event) -> None:
        seen.append(ev)

    await event_bus.dispatch(Event(name="document.failed", source="test"))
    assert seen == []


@pytest.mark.asyncio
async def test_handler_exception_does_not_break_dispatch():
    seen: list[str] = []

    @event_bus.on("governance.alert")
    async def _broken(ev: Event) -> None:
        raise RuntimeError("boom")

    @event_bus.on("governance.alert")
    async def _good(ev: Event) -> None:
        seen.append("good")

    await event_bus.dispatch(Event(name="governance.alert", source="test"))
    assert seen == ["good"]


@pytest.mark.asyncio
async def test_publish_never_raises_on_redis_down(monkeypatch):
    # Point REDIS_URL at a closed port — publish() should log + swallow.
    from app.core import config as core_cfg
    monkeypatch.setattr(core_cfg.settings, "REDIS_URL", "redis://127.0.0.1:1")
    await event_bus.publish(Event(name="document.completed", source="test"))
