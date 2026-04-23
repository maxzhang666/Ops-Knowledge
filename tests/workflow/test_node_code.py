from unittest.mock import AsyncMock, patch

import pytest

from app.workflow.nodes._code import CodeNode
from app.workflow.nodes.base import NodeContext
from app.workflow.runner_client import RunnerError


def _ctx(code: str = "outputs['x']=1", timeout: float = 5, inputs: dict | None = None) -> NodeContext:
    return NodeContext(
        node_id="c", node_type="code",
        inputs=inputs or {},
        config={"code": code, "timeout": timeout, "language": "python"},
    )


@pytest.mark.asyncio
async def test_validate_rejects_missing_code():
    node = CodeNode()
    ctx = NodeContext(node_id="c", node_type="code", config={"language": "python"})
    with pytest.raises(ValueError, match="missing 'code'"):
        await node.validate(ctx)


@pytest.mark.asyncio
async def test_validate_rejects_non_python():
    node = CodeNode()
    ctx = NodeContext(node_id="c", node_type="code", config={"code": "x", "language": "js"})
    with pytest.raises(ValueError, match="only 'python'"):
        await node.validate(ctx)


@pytest.mark.asyncio
async def test_execute_ok_path():
    node = CodeNode()
    with patch(
        "app.workflow.nodes._code.RunnerClient",
    ) as RC:
        instance = RC.return_value
        instance.execute = AsyncMock(return_value={
            "ok": True, "outputs": {"y": 4}, "stdout": "hi", "stderr": "", "error": None,
            "request_id": "r", "duration_ms": 5,
        })
        res = await node.execute(_ctx(inputs={"x": 2}))
    assert res.outputs == {"y": 4}
    assert res.debug == {"stdout": "hi", "stderr": ""}


@pytest.mark.asyncio
async def test_execute_runner_not_ok_raises():
    node = CodeNode()
    with patch("app.workflow.nodes._code.RunnerClient") as RC:
        instance = RC.return_value
        instance.execute = AsyncMock(return_value={
            "ok": False, "error": "timeout: wall-clock 0.3s exceeded",
            "request_id": "r", "duration_ms": 300, "stdout": "", "stderr": "",
        })
        with pytest.raises(RuntimeError, match="timeout"):
            await node.execute(_ctx())


@pytest.mark.asyncio
async def test_execute_runner_unreachable_raises():
    node = CodeNode()
    with patch("app.workflow.nodes._code.RunnerClient") as RC:
        instance = RC.return_value
        instance.execute = AsyncMock(side_effect=RunnerError("refused"))
        with pytest.raises(RuntimeError, match="Runner unreachable"):
            await node.execute(_ctx())
