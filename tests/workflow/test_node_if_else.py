import pytest

from app.workflow.context import ExecutionContext
from app.workflow.nodes._if_else import IfElseNode
from app.workflow.nodes.base import NodeContext


def _ctx(conditions, inputs=None, outputs_by_node=None):
    ec = ExecutionContext()
    for nid, out in (outputs_by_node or {}).items():
        ec.record_output(nid, out)
    return NodeContext(
        node_id="c", node_type="if-else",
        inputs=inputs or {},
        config={"conditions": conditions},
        execution_context=ec,
    )


@pytest.mark.asyncio
async def test_validate_rejects_empty():
    node = IfElseNode()
    with pytest.raises(ValueError, match="at least one"):
        await node.validate(NodeContext(node_id="c", node_type="if-else", config={"conditions": []}))


@pytest.mark.asyncio
async def test_and_logic_all_must_match():
    node = IfElseNode()
    ctx = _ctx(
        conditions=[{
            "id": "ok", "logic": "and",
            "rules": [
                {"variable": "x", "operator": "gt", "value": 5},
                {"variable": "x", "operator": "lt", "value": 10},
            ],
        }],
        inputs={"x": 7},
    )
    res = await node.execute(ctx)
    assert res.branch == "ok"


@pytest.mark.asyncio
async def test_or_logic_any_match():
    node = IfElseNode()
    ctx = _ctx(
        conditions=[{
            "id": "any", "logic": "or",
            "rules": [
                {"variable": "x", "operator": "eq", "value": 1},
                {"variable": "x", "operator": "eq", "value": 99},
            ],
        }],
        inputs={"x": 99},
    )
    res = await node.execute(ctx)
    assert res.branch == "any"


@pytest.mark.asyncio
async def test_no_match_else_branch():
    node = IfElseNode()
    ctx = _ctx(
        conditions=[{"id": "c1", "rules": [{"variable": "x", "operator": "eq", "value": "none"}]}],
        inputs={"x": "something"},
    )
    res = await node.execute(ctx)
    assert res.branch == "else"


@pytest.mark.asyncio
async def test_selector_lhs_from_upstream_node():
    node = IfElseNode()
    ctx = _ctx(
        conditions=[{
            "id": "match",
            "rules": [{"variable": ["up", "count"], "operator": "gt", "value": 0}],
        }],
        outputs_by_node={"up": {"count": 5}},
    )
    res = await node.execute(ctx)
    assert res.branch == "match"


@pytest.mark.asyncio
async def test_is_empty_operator():
    node = IfElseNode()
    ctx = _ctx(
        conditions=[{"id": "e", "rules": [{"variable": "x", "operator": "is_empty"}]}],
        inputs={"x": []},
    )
    assert (await node.execute(ctx)).branch == "e"


@pytest.mark.asyncio
async def test_unknown_operator_rejected():
    node = IfElseNode()
    ctx = _ctx(
        conditions=[{"id": "x", "rules": [{"variable": "a", "operator": "not_real"}]}],
        inputs={"a": 1},
    )
    with pytest.raises(ValueError, match="unknown operator"):
        await node.execute(ctx)
