import pytest

from app.workflow.nodes._variable_splitter import VariableSplitterNode
from app.workflow.nodes.base import NodeContext


def _ctx(source, mapping):
    return NodeContext(
        node_id="vs", node_type="variable-splitter",
        inputs={"source": source},
        config={"mapping": mapping},
    )


@pytest.mark.asyncio
async def test_happy_path_flat():
    node = VariableSplitterNode()
    res = await node.execute(_ctx({"a": 1, "b": 2}, {"x": "a", "y": "b"}))
    assert res.outputs == {"x": 1, "y": 2}


@pytest.mark.asyncio
async def test_nested_and_list_path():
    node = VariableSplitterNode()
    src = {"items": [{"id": "c1"}, {"id": "c2"}]}
    res = await node.execute(_ctx(src, {"first_id": "items.0.id"}))
    assert res.outputs == {"first_id": "c1"}


@pytest.mark.asyncio
async def test_missing_path_fails_loudly():
    node = VariableSplitterNode()
    with pytest.raises(RuntimeError, match="path 'missing' failed"):
        await node.execute(_ctx({"a": 1}, {"x": "missing"}))


@pytest.mark.asyncio
async def test_validate_requires_source_and_mapping():
    node = VariableSplitterNode()
    with pytest.raises(ValueError, match="mapping required"):
        await node.validate(NodeContext(node_id="vs", node_type="variable-splitter",
                                          inputs={"source": {}}, config={}))
    with pytest.raises(ValueError, match="'source' input required"):
        await node.validate(NodeContext(node_id="vs", node_type="variable-splitter",
                                          inputs={}, config={"mapping": {"x": "a"}}))
