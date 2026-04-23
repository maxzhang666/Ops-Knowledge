import pytest

from app.workflow.context import ExecutionContext, SelectorError


def test_selector_basic():
    ctx = ExecutionContext()
    ctx.record_output("n1", {"content": "hello"})
    assert ctx.resolve_selector(["n1", "content"]) == "hello"


def test_selector_nested_dict_and_list():
    ctx = ExecutionContext()
    ctx.record_output("r", {"chunks": [{"id": "c1"}, {"id": "c2"}]})
    assert ctx.resolve_selector(["r", "chunks", "0", "id"]) == "c1"
    assert ctx.resolve_selector(["r", "chunks", "1", "id"]) == "c2"


def test_selector_unknown_node_raises():
    ctx = ExecutionContext()
    with pytest.raises(SelectorError, match="no recorded output"):
        ctx.resolve_selector(["missing", "f"])


def test_selector_unknown_field_raises():
    ctx = ExecutionContext()
    ctx.record_output("n", {"a": 1})
    with pytest.raises(SelectorError, match="not found"):
        ctx.resolve_selector(["n", "b"])


def test_template_node_reference():
    ctx = ExecutionContext()
    ctx.record_output("llm", {"content": "world"})
    assert ctx.resolve_template("hello {{#llm.content#}}!") == "hello world!"


def test_template_workflow_var_simple():
    ctx = ExecutionContext(workflow_variables={"greeting": "hi"})
    assert ctx.resolve_template("{{vars.greeting}} there") == "hi there"


def test_template_workflow_var_nested():
    ctx = ExecutionContext(trigger_input={"user": {"name": "Max"}})
    assert ctx.resolve_template("Hi {{vars.trigger.user.name}}") == "Hi Max"


def test_template_unknown_var_raises():
    ctx = ExecutionContext()
    with pytest.raises(SelectorError, match="not defined"):
        ctx.resolve_template("{{vars.ghost}}")


def test_trigger_input_injected_into_vars():
    ctx = ExecutionContext(trigger_input={"query": "q"})
    assert ctx.resolve_selector(["vars", "trigger", "query"]) == "q"


def test_plain_text_passthrough():
    ctx = ExecutionContext()
    assert ctx.resolve_template("no placeholders here") == "no placeholders here"
