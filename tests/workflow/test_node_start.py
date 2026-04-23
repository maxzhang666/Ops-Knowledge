import pytest

from app.workflow.context import ExecutionContext
from app.workflow.nodes._start import StartNode
from app.workflow.nodes.base import NodeContext


def _ctx(trigger: dict | None = None, variables: list | None = None) -> NodeContext:
    ec = ExecutionContext(trigger_input=trigger or {})
    return NodeContext(
        node_id="s", node_type="start",
        config={"variables": variables} if variables is not None else {},
        execution_context=ec,
    )


@pytest.mark.asyncio
async def test_zero_config_passes_trigger_through():
    node = StartNode()
    res = await node.execute(_ctx(trigger={"msg": "hi"}))
    assert res.outputs == {"msg": "hi"}


@pytest.mark.asyncio
async def test_required_variable_missing_rejected():
    node = StartNode()
    with pytest.raises(ValueError, match="required"):
        await node.validate(_ctx(
            trigger={},
            variables=[{"name": "query", "type": "string", "required": True}],
        ))


@pytest.mark.asyncio
async def test_declared_variable_coerce_to_number():
    node = StartNode()
    res = await node.execute(_ctx(
        trigger={"n": "42"},
        variables=[{"name": "n", "type": "number"}],
    ))
    assert res.outputs == {"n": 42}


@pytest.mark.asyncio
async def test_optional_variable_default_fills():
    node = StartNode()
    res = await node.execute(_ctx(
        trigger={},
        variables=[{"name": "lang", "type": "string", "default": "en"}],
    ))
    assert res.outputs == {"lang": "en"}


@pytest.mark.asyncio
async def test_boolean_coercion():
    node = StartNode()
    res = await node.execute(_ctx(
        trigger={"flag": "true"},
        variables=[{"name": "flag", "type": "boolean"}],
    ))
    assert res.outputs == {"flag": True}
