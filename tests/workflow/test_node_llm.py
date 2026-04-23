import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workflow.nodes._llm import LLMNode
from app.workflow.nodes.base import NodeContext


def _ctx(streaming: bool, inputs: dict | None = None) -> NodeContext:
    return NodeContext(
        node_id="llm", node_type="llm",
        inputs=inputs or {"query": "Q"},
        config={
            "model_provider_id": str(uuid.uuid4()),
            "model_name": "gpt-fake",
            "streaming": streaming,
            "prompt_template": [
                {"role": "system", "text": "You answer {query}."},
                {"role": "user", "text": "{query}"},
            ],
        },
    )


@pytest.mark.asyncio
async def test_validate_rejects_missing_template():
    node = LLMNode()
    ctx = NodeContext(
        node_id="llm", node_type="llm",
        config={"model_provider_id": "x", "model_name": "y"},
    )
    with pytest.raises(ValueError, match="prompt_template"):
        await node.validate(ctx)


@pytest.mark.asyncio
async def test_non_streaming_returns_content():
    node = LLMNode()

    class _Sess:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    sess = _Sess()

    svc = MagicMock()
    svc.chat = AsyncMock(return_value={
        "choices": [{"message": {"content": "hi there"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    })

    with patch("app.workflow.nodes._llm.async_session", return_value=sess), \
         patch("app.workflow.nodes._llm.ModelService", return_value=svc):
        res = await node.execute(_ctx(streaming=False))

    assert res.outputs["content"] == "hi there"
    assert res.outputs["token_usage"] == {"prompt_tokens": 3, "completion_tokens": 2}


@pytest.mark.asyncio
async def test_streaming_accumulates_deltas():
    node = LLMNode()

    class _Sess:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    async def _stream(*args, **kwargs):
        for piece in ("hi ", "there"):
            yield {"choices": [{"delta": {"content": piece}}]}
        yield {"usage": {"prompt_tokens": 3, "completion_tokens": 2}, "choices": []}

    svc = MagicMock()
    svc.chat_stream = _stream

    with patch("app.workflow.nodes._llm.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._llm.ModelService", return_value=svc):
        res = await node.execute(_ctx(streaming=True))

    assert res.outputs["content"] == "hi there"
    assert res.outputs["token_usage"] == {"prompt_tokens": 3, "completion_tokens": 2}


@pytest.mark.asyncio
async def test_prompt_template_substitution():
    node = LLMNode()
    captured: dict = {}

    class _Sess:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    async def _chat(pid, model, messages, **kw):
        captured["messages"] = messages
        return {"choices": [{"message": {"content": "x"}}], "usage": {}}

    svc = MagicMock()
    svc.chat = _chat

    with patch("app.workflow.nodes._llm.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._llm.ModelService", return_value=svc):
        await node.execute(_ctx(streaming=False, inputs={"query": "what is X?"}))

    assert captured["messages"][0]["content"] == "You answer what is X?."
    assert captured["messages"][1]["content"] == "what is X?"
