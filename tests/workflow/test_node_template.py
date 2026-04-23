import pytest

from app.workflow.nodes._template import TemplateNode
from app.workflow.nodes.base import NodeContext


def _ctx(template: str, inputs: dict | None = None) -> NodeContext:
    return NodeContext(
        node_id="t", node_type="template",
        inputs=inputs or {},
        config={"template": template},
    )


@pytest.mark.asyncio
async def test_render_happy_path():
    node = TemplateNode()
    res = await node.execute(_ctx("Hello {{ name }}!", {"name": "World"}))
    assert res.outputs["output"] == "Hello World!"


@pytest.mark.asyncio
async def test_strict_undefined_raises_on_missing_var():
    node = TemplateNode()
    with pytest.raises(RuntimeError, match="render failed"):
        await node.execute(_ctx("hi {{ ghost }}"))


@pytest.mark.asyncio
async def test_invalid_syntax_caught_at_validate():
    node = TemplateNode()
    with pytest.raises(ValueError, match="invalid Jinja2 syntax"):
        await node.validate(_ctx("{% if broken"))


@pytest.mark.asyncio
async def test_sandbox_blocks_escape_attempt():
    node = TemplateNode()
    # Accessing __class__ in a sandboxed env raises SecurityError at render.
    with pytest.raises(RuntimeError):
        await node.execute(_ctx('{{ "".__class__ }}'))


@pytest.mark.asyncio
async def test_loops_and_conditionals():
    node = TemplateNode()
    res = await node.execute(_ctx(
        "{% for x in items %}{{ x }},{% endfor %}",
        {"items": [1, 2, 3]},
    ))
    assert res.outputs["output"] == "1,2,3,"
