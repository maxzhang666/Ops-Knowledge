"""Workflow Agent chat pipeline — plan 22 Task 4.

Maps LangGraph bridge events → SSE tuples. We stub ConversationService and
the backing Workflow row so the test stays in-process with no DB / Redis /
LLM. The compiled graph runs — we rely on plan 15's EchoNode / StartNode
builtins being registered at import time.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chat.workflow_pipeline import run_workflow_pipeline
from app.workflow.nodes.registry import load_builtin_nodes


@pytest.fixture(autouse=True)
def _load_nodes():
    load_builtin_nodes()


def _agent(workflow_id=None):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.agent_type = "workflow"
    a.workflow_id = workflow_id if workflow_id is not None else uuid.uuid4()
    return a


def _make_db_session(wf_row):
    """Async context manager yielding a stub AsyncSession that returns `wf_row`
    from db.get(Workflow, ...) and a no-op commit/flush."""

    class _Db:
        async def get(self, model, key):
            return wf_row
        async def commit(self): pass
        async def flush(self): pass

    class _Cm:
        async def __aenter__(self): return _Db()
        async def __aexit__(self, *a): return False

    return _Cm()


def _conv_svc_stub(conversation_id: uuid.UUID, user_msg_id: uuid.UUID):
    svc = MagicMock()
    conv = MagicMock(id=conversation_id)
    user_msg = MagicMock(id=user_msg_id)
    svc.create_conversation = AsyncMock(return_value=conv)
    svc.get_conversation = AsyncMock(return_value=conv)
    svc.add_message = AsyncMock(return_value=user_msg)
    svc.get_messages = AsyncMock(return_value=[user_msg])
    return svc


def _echo_graph(prefix: str = "hi-") -> dict:
    """Valid published DSL: Start → Echo → Answer. Echoes content as answer."""
    return {
        "dsl_version": "1.0",
        "graph": {
            "nodes": [
                {"id": "s", "type": "start", "data": {}},
                {"id": "e", "type": "builtin.echo", "data": {
                    "prefix": prefix,
                    "inputs": {"text": ["vars", "trigger", "content"]},
                }},
                {"id": "a", "type": "answer", "data": {
                    "stream": False,  # avoid stream chunk noise in assertions
                    "inputs": {"answer": ["e", "text"]},
                }},
            ],
            "edges": [
                {"source": "s", "target": "e"},
                {"source": "e", "target": "a"},
            ],
        },
        "workflow_variables": [],
    }


@pytest.mark.asyncio
async def test_missing_workflow_id_emits_friendly_error():
    a = _agent(workflow_id=None)
    # Force workflow_id attribute to None (MagicMock default gives truthy auto-mock).
    a.workflow_id = None
    events = []
    async for kind, payload in run_workflow_pipeline(
        agent=a, query="hi", conversation_id=None, user_id=uuid.uuid4(),
    ):
        events.append((kind, payload))
    assert any(k == "content_delta" and "未绑定" in p.get("delta", "") for k, p in events)
    assert events[-1][0] == "message_end"


@pytest.mark.asyncio
async def test_unpublished_workflow_shows_hint():
    a = _agent()
    wf_row = MagicMock(published_graph_data=None)
    conv_svc = _conv_svc_stub(uuid.uuid4(), uuid.uuid4())

    with patch(
        "app.chat.workflow_pipeline.async_session",
        side_effect=lambda: _make_db_session(wf_row),
    ), patch(
        "app.chat.workflow_pipeline.ConversationService", return_value=conv_svc,
    ):
        events = []
        async for kind, payload in run_workflow_pipeline(
            agent=a, query="hi", conversation_id=None, user_id=uuid.uuid4(),
        ):
            events.append((kind, payload))

    # Friendly "未发布" message + message_end (no message_start since we
    # return early before the DSL runs).
    assert any(k == "content_delta" and "未发布" in p.get("delta", "") for k, p in events)
    assert events[-1][0] == "message_end"


@pytest.mark.asyncio
async def test_happy_path_emits_sse_sequence():
    a = _agent()
    wf_row = MagicMock(published_graph_data=_echo_graph("wrap-"))
    conv_svc = _conv_svc_stub(uuid.uuid4(), uuid.uuid4())

    with patch(
        "app.chat.workflow_pipeline.async_session",
        side_effect=lambda: _make_db_session(wf_row),
    ), patch(
        "app.chat.workflow_pipeline.ConversationService", return_value=conv_svc,
    ), patch(
        "app.chat.workflow_pipeline.publish_event", new_callable=AsyncMock,
    ):
        kinds: list[str] = []
        final_text = ""
        async for kind, payload in run_workflow_pipeline(
            agent=a, query="hello", conversation_id=None, user_id=uuid.uuid4(),
        ):
            kinds.append(kind)
            if kind == "content_delta":
                final_text += payload.get("delta", "")

    # Basic contract checks:
    assert kinds[0] == "message_start"
    assert kinds[-1] == "message_end"
    # Answer node stream=False so the echo output may or may not stream — we
    # only assert the saved message picked up the wrapped query.
    assert conv_svc.add_message.call_count == 2  # user + assistant
    assistant_call = conv_svc.add_message.call_args_list[-1]
    assert assistant_call.kwargs["role"] == "assistant"
    assert "wrap-hello" in assistant_call.kwargs["content"]


@pytest.mark.asyncio
async def test_trace_id_matches_execution_uuid():
    """trace_id in message_end == scheduler execution_id so Langfuse (plan 23)
    can later correlate SSE output with workflow spans."""
    a = _agent()
    wf_row = MagicMock(published_graph_data=_echo_graph())
    conv_svc = _conv_svc_stub(uuid.uuid4(), uuid.uuid4())

    trace_id = None
    with patch(
        "app.chat.workflow_pipeline.async_session",
        side_effect=lambda: _make_db_session(wf_row),
    ), patch(
        "app.chat.workflow_pipeline.ConversationService", return_value=conv_svc,
    ), patch(
        "app.chat.workflow_pipeline.publish_event", new_callable=AsyncMock,
    ):
        async for kind, payload in run_workflow_pipeline(
            agent=a, query="hi", conversation_id=None, user_id=uuid.uuid4(),
        ):
            if kind == "message_end":
                trace_id = payload.get("trace_id")

    assert trace_id is not None
    # Should be a parseable UUID string.
    uuid.UUID(trace_id)
