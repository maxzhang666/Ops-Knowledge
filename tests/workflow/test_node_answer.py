import pytest

from app.workflow.nodes._answer import AnswerNode
from app.workflow.nodes.base import NodeContext


def _ctx(answer: str | None = None, stream: bool = True) -> NodeContext:
    inputs = {"answer": answer} if answer is not None else {}
    return NodeContext(
        node_id="a", node_type="answer",
        inputs=inputs, config={"stream": stream},
    )


@pytest.mark.asyncio
async def test_execute_passes_through():
    node = AnswerNode()
    res = await node.execute(_ctx(answer="final text"))
    assert res.outputs == {"answer": "final text"}


@pytest.mark.asyncio
async def test_validate_requires_answer_input():
    node = AnswerNode()
    with pytest.raises(ValueError, match="missing 'answer'"):
        await node.validate(_ctx(answer=None))


@pytest.mark.asyncio
async def test_stream_chunks_text():
    node = AnswerNode()
    ctx = _ctx(answer="a" * 40)
    chunks = [c.delta async for c in node.on_stream(ctx)]
    assert "".join(chunks) == "a" * 40
    assert len(chunks) == 3  # 16 + 16 + 8


@pytest.mark.asyncio
async def test_stream_disabled_yields_nothing():
    node = AnswerNode()
    ctx = _ctx(answer="abc", stream=False)
    chunks = [c async for c in node.on_stream(ctx)]
    assert chunks == []
