import pytest

from app.workflow.nodes.base import (
    AbstractNode,
    BaseNode,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)


class _Dummy(AbstractNode):
    manifest = NodeManifest(
        type="test.dummy", category="extension", name="Dummy",
    )
    io = NodeIO(
        inputs={"x": {"type": "number"}},
        outputs={"y": {"type": "number"}},
    )

    async def execute(self, ctx: NodeContext) -> NodeResult:
        return NodeResult(outputs={"y": ctx.inputs["x"] * 2})


@pytest.mark.asyncio
async def test_abstract_node_execute():
    n = _Dummy()
    res = await n.execute(
        NodeContext(node_id="n1", node_type="test.dummy", inputs={"x": 3})
    )
    assert res.outputs == {"y": 6}


def test_node_satisfies_protocol():
    assert isinstance(_Dummy(), BaseNode)


def test_manifest_frozen():
    m = NodeManifest(type="t", category="extension", name="T")
    with pytest.raises(Exception):
        m.type = "other"  # frozen — mutation forbidden


@pytest.mark.asyncio
async def test_default_on_stream_yields_nothing():
    n = _Dummy()
    ctx = NodeContext(node_id="n1", node_type="test.dummy")
    chunks = [c async for c in n.on_stream(ctx)]
    assert chunks == []


@pytest.mark.asyncio
async def test_default_on_error_returns_none():
    n = _Dummy()
    ctx = NodeContext(node_id="n1", node_type="test.dummy")
    assert await n.on_error(ctx, RuntimeError("boom")) is None
