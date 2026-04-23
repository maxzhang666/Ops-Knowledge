"""Per-match-type + handler validation — B1/B3/B5 (workflow-only scope, Plan 31)."""
import uuid

import pytest
from pydantic import ValidationError

from app.agent.orchestrator.schemas import (
    AgentRuleCreate,
    AgentRuleUpdate,
    ConditionMatchConfig,
    WorkflowHandlerConfig,
)


def _hid():
    return uuid.uuid4()


def test_keyword_ok():
    r = AgentRuleCreate(
        match_type="keyword",
        match_config={"any_of": ["foo", "bar"]},
        handler_type="workflow",
        handler_id=_hid(),
    )
    assert r.match_config["any_of"] == ["foo", "bar"]
    assert r.match_config["case_sensitive"] is False  # default
    assert r.handler_config == {"input_mapping": {"query": "$message"}}


def test_keyword_wrong_shape_rejected():
    with pytest.raises(ValidationError):
        AgentRuleCreate(
            match_type="keyword",
            match_config={"contain": "foo"},  # wrong key
            handler_type="workflow",
            handler_id=_hid(),
        )


def test_condition_op_list_mismatch():
    with pytest.raises(ValidationError):
        ConditionMatchConfig(path="user.role", op="==", value=["admin"])  # list w/ ==
    with pytest.raises(ValidationError):
        ConditionMatchConfig(path="user.role", op="in", value="admin")  # scalar w/ in


def test_condition_valid():
    c = ConditionMatchConfig(path="user.role", op="==", value="admin")
    assert c.op == "=="


def test_regex_invalid_pattern_rejected():
    with pytest.raises(ValidationError):
        AgentRuleCreate(
            match_type="regex",
            match_config={"pattern": "(unterminated"},
            handler_type="workflow",
            handler_id=_hid(),
        )


def test_regex_valid():
    r = AgentRuleCreate(
        match_type="regex",
        match_config={"pattern": "foo|bar", "flags": "i"},
        handler_type="workflow",
        handler_id=_hid(),
    )
    assert r.match_config["flags"] == "i"


def test_handler_id_required_for_workflow():
    """handler_id must point to a workflow — rejected when null (B1)."""
    with pytest.raises(ValidationError):
        AgentRuleCreate(
            match_type="keyword",
            match_config={"any_of": ["x"]},
            handler_type="workflow",
            handler_id=None,
        )


def test_non_workflow_handler_type_rejected():
    """Plan 31 scope locks handler_type to 'workflow'. Other values
    (simple_agent / mcp_tool / sub_agent) are unlocked only by lifting
    the Literal in schemas.py — a deliberate control point."""
    with pytest.raises(ValidationError):
        AgentRuleCreate(
            match_type="keyword",
            match_config={"any_of": ["x"]},
            handler_type="simple_agent",
            handler_id=_hid(),
        )


def test_workflow_custom_input_mapping():
    """Custom input_mapping with multiple variables — common case for
    passing user message + extra context into a Workflow."""
    r = AgentRuleCreate(
        match_type="keyword",
        match_config={"any_of": ["x"]},
        handler_type="workflow",
        handler_id=_hid(),
        handler_config={
            "input_mapping": {
                "query": "$message",
                "dept_id": "$user.department_id",
            },
        },
    )
    assert r.handler_config["input_mapping"]["dept_id"] == "$user.department_id"


def test_workflow_handler_default_input_mapping():
    cfg = WorkflowHandlerConfig()
    assert cfg.input_mapping == {"query": "$message"}


def test_update_transport_change_requires_config():
    with pytest.raises(ValidationError):
        AgentRuleUpdate(match_type="keyword")


def test_update_extra_forbidden():
    with pytest.raises(ValidationError):
        AgentRuleUpdate(bogus=1)
