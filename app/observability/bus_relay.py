"""Cross-domain bus events → Langfuse independent traces.

Plan 23 Task 5. These aren't parented to any chat/workflow trace — they're
ops-dashboard observations (doc processing, reindex, governance alerts).
Imported at app startup so @on decorators register before the bus subscriber
starts consuming.
"""
from __future__ import annotations

import logging

from app.core.observability import get_client
from app.integration.event_bus import on
from app.integration.events import Event

log = logging.getLogger(__name__)


def _relay(event: Event) -> None:
    """Common helper — one Langfuse trace per bus event."""
    try:
        client = get_client()
        trace = client.trace(
            name=event.name,
            metadata={"source": event.source, **event.data},
        )
        trace.end()
    except Exception as e:  # noqa: BLE001
        log.warning("bus_relay failed for %s: %s", event.name, e)


@on("document.completed")
async def _on_document_completed(event: Event) -> None:
    _relay(event)


@on("document.failed")
async def _on_document_failed(event: Event) -> None:
    _relay(event)


@on("kb.reindex_completed")
async def _on_reindex_completed(event: Event) -> None:
    _relay(event)


@on("workflow.execution_completed")
async def _on_wf_completed(event: Event) -> None:
    _relay(event)


@on("workflow.execution_failed")
async def _on_wf_failed(event: Event) -> None:
    _relay(event)


@on("governance.alert")
async def _on_governance_alert(event: Event) -> None:
    _relay(event)
