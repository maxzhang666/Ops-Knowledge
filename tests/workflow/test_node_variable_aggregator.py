import pytest

from app.workflow.nodes._variable_aggregator import VariableAggregatorNode
from app.workflow.nodes.base import NodeContext


def _ctx(inputs: dict, mode: str = "first_non_null") -> NodeContext:
    return NodeContext(
        node_id="v", node_type="variable-aggregator",
        inputs=inputs, config={"mode": mode},
    )


@pytest.mark.asyncio
async def test_first_non_null_picks_first_useful():
    node = VariableAggregatorNode()
    res = await node.execute(_ctx({"a": None, "b": "", "c": "pick me"}))
    assert res.outputs == {"output": "pick me"}


@pytest.mark.asyncio
async def test_first_non_null_all_empty_yields_none():
    node = VariableAggregatorNode()
    res = await node.execute(_ctx({"a": None, "b": ""}))
    assert res.outputs == {"output": None}


@pytest.mark.asyncio
async def test_array_filters_none_but_keeps_empty_string():
    node = VariableAggregatorNode()
    res = await node.execute(_ctx({"a": 1, "b": None, "c": ""}, mode="array"))
    assert res.outputs == {"output": [1, ""]}


@pytest.mark.asyncio
async def test_merge_object_ignores_non_dicts():
    node = VariableAggregatorNode()
    res = await node.execute(_ctx(
        {"a": {"x": 1}, "b": "not a dict", "c": {"y": 2, "x": 10}},
        mode="merge_object",
    ))
    # Later dict overrides earlier (c overrides a on x).
    assert res.outputs == {"output": {"x": 10, "y": 2}}


@pytest.mark.asyncio
async def test_unknown_mode_rejected():
    node = VariableAggregatorNode()
    with pytest.raises(ValueError, match="unknown mode"):
        await node.execute(_ctx({}, mode="whatever"))
