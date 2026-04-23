"""Per-match-type + per-handler-type validation — B1/B3/B5."""
import uuid

import pytest
from pydantic import ValidationError

from app.agent.orchestrator.schemas import (
    AgentRuleCreate,
    AgentRuleUpdate,
    ConditionMatchConfig,
    MCPToolHandlerConfig,
    WorkflowHandlerConfig,
)


def _hid():
    return uuid.uuid4()


def test_keyword_ok():
    r = AgentRuleCreate(
        match_type="keyword",
        match_config={"any_of": ["foo", "bar"]},
        handler_type="simple_agent",
        handler_id=_hid(),
    )
    assert r.match_config["any_of"] == ["foo", "bar"]
    assert r.match_config["case_sensitive"] is False  # default


def test_keyword_wrong_shape_rejected():
    with pytest.raises(ValidationError):
        AgentRuleCreate(
            match_type="keyword",
            match_config={"contain": "foo"},  # wrong key
            handler_type="simple_agent",
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
            handler_type="simple_agent",
            handler_id=_hid(),
        )


def test_regex_valid():
    r = AgentRuleCreate(
        match_type="regex",
        match_config={"pattern": "foo|bar", "flags": "i"},
        handler_type="simple_agent",
        handler_id=_hid(),
    )
    assert r.match_config["flags"] == "i"


def test_handler_id_required_for_simple_agent():
    with pytest.raises(ValidationError):
        AgentRuleCreate(
            match_type="keyword",
            match_config={"any_of": ["x"]},
            handler_type="simple_agent",
            handler_id=None,
        )


def test_handler_id_required_for_mcp_tool_and_config_validated():
    # mcp_tool 要 handler_id + tool_name
    with pytest.raises(ValidationError):
        AgentRuleCreate(
            match_type="keyword",
            match_config={"any_of": ["x"]},
            handler_type="mcp_tool",
            handler_id=_hid(),  # missing tool_name
            handler_config={},
        )
    # good
    r = AgentRuleCreate(
        match_type="keyword",
        match_config={"any_of": ["x"]},
        handler_type="mcp_tool",
        handler_id=_hid(),
        handler_config={"tool_name": "get_ticket"},
    )
    assert r.handler_config["tool_name"] == "get_ticket"


def test_workflow_handler_default_input_mapping():
    cfg = WorkflowHandlerConfig()
    assert cfg.input_mapping == {"query": "$message"}


def test_update_transport_change_requires_config():
    with pytest.raises(ValidationError):
        AgentRuleUpdate(match_type="keyword")


def test_update_extra_forbidden():
    with pytest.raises(ValidationError):
        AgentRuleUpdate(bogus=1)
