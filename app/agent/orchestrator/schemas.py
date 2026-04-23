"""Per-match-type + per-handler-type Pydantic validation.

Rule payloads are a tagged union: ``match_type`` picks the ``match_config``
validator, ``handler_type`` picks the ``handler_config`` validator. Ops
writing bad config (e.g. ``{"contain": "x"}`` instead of ``{"any_of": [...]}``)
get a 422 at create time, not a runtime failure mid-chat.

Same pattern as ``MCPServerCreate`` cross-field validation (Plan 30 M1).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ── Match config per type ────────────────────────────────────────

CONDITION_OPERATORS = {"==", "!=", "in", "not_in", ">", "<", ">=", "<="}


class ConditionMatchConfig(BaseModel):
    """Metadata condition. ``path`` only references trusted metadata
    namespace (enforced at create time against Agent.orchestrator_config.
    trusted_metadata_paths — see matchers/condition.py for runtime check
    and ``validate_against_trusted`` below)."""
    path: str = Field(..., min_length=1, max_length=200)  # e.g. "user.role"
    op: Literal["==", "!=", "in", "not_in", ">", "<", ">=", "<="]
    value: str | int | float | bool | list[str | int | float]

    @model_validator(mode="after")
    def _check_shape(self):
        if self.op in ("in", "not_in") and not isinstance(self.value, list):
            raise ValueError(f"op '{self.op}' requires a list value")
        if self.op not in ("in", "not_in") and isinstance(self.value, list):
            raise ValueError(f"op '{self.op}' does not accept a list value")
        return self


class KeywordMatchConfig(BaseModel):
    any_of: list[str] = Field(..., min_length=1)
    case_sensitive: bool = False


class RegexMatchConfig(BaseModel):
    pattern: str = Field(..., min_length=1, max_length=1000)
    flags: str = Field("", pattern=r"^[ims]*$")  # i / m / s subset

    @model_validator(mode="after")
    def _compile(self):
        try:
            re.compile(self.pattern, _flags_to_re(self.flags))
        except re.error as e:
            raise ValueError(f"invalid regex: {e}") from e
        return self


class LLMIntentMatchConfig(BaseModel):
    # Must match a category defined on the Agent's classifier. Cross-check
    # happens in the service layer since it needs Agent context.
    category: str = Field(..., min_length=1, max_length=100)


MATCH_SCHEMAS: dict[str, type[BaseModel]] = {
    "condition": ConditionMatchConfig,
    "keyword": KeywordMatchConfig,
    "regex": RegexMatchConfig,
    "llm_intent": LLMIntentMatchConfig,
}


# ── Handler config per type ──────────────────────────────────────

class SimpleAgentHandlerConfig(BaseModel):
    # Reserved slot for future per-route overrides (system_prompt etc.)
    model_config = {"extra": "forbid"}


class WorkflowHandlerConfig(BaseModel):
    # Default: map the user message to the workflow's ``query`` var.
    # Each value is a template string; ``$message`` / ``$metadata.foo`` /
    # ``$user.id`` resolved at dispatch time.
    input_mapping: dict[str, str] = Field(default_factory=lambda: {"query": "$message"})


class MCPToolHandlerConfig(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=200)
    arg_template: dict[str, str] = Field(default_factory=lambda: {"input": "$message"})


class SubAgentHandlerConfig(BaseModel):
    model_config = {"extra": "forbid"}


HANDLER_SCHEMAS: dict[str, type[BaseModel]] = {
    "simple_agent": SimpleAgentHandlerConfig,
    "workflow": WorkflowHandlerConfig,
    "mcp_tool": MCPToolHandlerConfig,
    "sub_agent": SubAgentHandlerConfig,
}

# handler_type → whether handler_id is required (skill deferred to P3)
HANDLER_ID_REQUIRED = {
    "simple_agent": True,
    "workflow": True,
    "mcp_tool": True,     # points to mcp_server_id
    "sub_agent": True,
}


# ── Rule CRUD schemas ────────────────────────────────────────────

MatchType = Literal["condition", "keyword", "regex", "llm_intent"]
HandlerType = Literal["simple_agent", "workflow", "mcp_tool", "sub_agent"]
OnHandlerError = Literal["use_default", "fallback_next", "return_error"]


def _normalize_match_config(match_type: str, raw: dict) -> dict:
    schema = MATCH_SCHEMAS.get(match_type)
    if schema is None:
        raise ValueError(f"Unsupported match_type: {match_type}")
    return schema.model_validate(raw).model_dump(exclude_none=False)


def _normalize_handler_config(handler_type: str, raw: dict) -> dict:
    schema = HANDLER_SCHEMAS.get(handler_type)
    if schema is None:
        raise ValueError(f"Unsupported handler_type: {handler_type}")
    return schema.model_validate(raw or {}).model_dump(exclude_none=False)


class AgentRuleCreate(BaseModel):
    priority: float | None = None  # null → service appends at end
    is_active: bool = True
    match_type: MatchType
    match_config: dict
    handler_type: HandlerType
    handler_id: uuid.UUID | None = None
    handler_config: dict = Field(default_factory=dict)
    on_handler_error: OnHandlerError = "use_default"

    @model_validator(mode="after")
    def _check(self):
        self.match_config = _normalize_match_config(self.match_type, self.match_config)
        self.handler_config = _normalize_handler_config(self.handler_type, self.handler_config)
        if HANDLER_ID_REQUIRED.get(self.handler_type) and self.handler_id is None:
            raise ValueError(f"handler_type '{self.handler_type}' requires handler_id")
        return self


class AgentRuleUpdate(BaseModel):
    is_active: bool | None = None
    match_type: MatchType | None = None
    match_config: dict | None = None
    handler_type: HandlerType | None = None
    handler_id: uuid.UUID | None = None
    handler_config: dict | None = None
    on_handler_error: OnHandlerError | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _check(self):
        # If changing match_type, a matching match_config must come with it
        if self.match_type is not None and self.match_config is None:
            raise ValueError("match_config is required when match_type changes")
        if self.match_config is not None and self.match_type is not None:
            self.match_config = _normalize_match_config(self.match_type, self.match_config)
        if self.handler_type is not None and self.handler_config is None:
            # Handler type change without config — accept as empty; defaults apply
            self.handler_config = _normalize_handler_config(self.handler_type, {})
        if self.handler_config is not None and self.handler_type is not None:
            self.handler_config = _normalize_handler_config(self.handler_type, self.handler_config)
        return self


class AgentRuleMove(BaseModel):
    """Drag-reorder payload. ``after_rule_id=null`` means "move to top"."""
    after_rule_id: uuid.UUID | None = None


class AgentRuleResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    priority: float
    is_active: bool
    version: int
    match_type: str
    match_config: dict
    handler_type: str
    handler_id: uuid.UUID | None
    handler_config: dict
    on_handler_error: str
    hit_count: int
    last_hit_at: datetime | None
    avg_latency_ms: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Orchestrator-level config ────────────────────────────────────

class ClassifierCategory(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    examples: list[str] = Field(default_factory=list)


class ClassifierConfig(BaseModel):
    model_registry_id: uuid.UUID
    categories: list[ClassifierCategory] = Field(..., min_length=1)
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0)
    cache_ttl_seconds: int = Field(300, ge=0, le=86400)
    fallback_on_low_confidence: Literal["default", "next"] = "default"


class DefaultHandler(BaseModel):
    handler_type: HandlerType
    handler_id: uuid.UUID | None = None
    handler_config: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self):
        self.handler_config = _normalize_handler_config(self.handler_type, self.handler_config)
        if HANDLER_ID_REQUIRED.get(self.handler_type) and self.handler_id is None:
            raise ValueError(f"handler_type '{self.handler_type}' requires handler_id")
        return self


# Default whitelist — spec 04 §Metadata trust.
DEFAULT_TRUSTED_PATHS = ["user.role", "user.department_id", "user.id"]
DEFAULT_DIAG_ROLES = ["system_admin", "dept_admin"]


class OrchestratorConfig(BaseModel):
    classifier: ClassifierConfig | None = None  # nullable: keyword/condition-only Agents
    default_handler: DefaultHandler
    trusted_metadata_paths: list[str] = Field(default_factory=lambda: list(DEFAULT_TRUSTED_PATHS))
    diagnostic_mode_allowed_roles: list[str] = Field(default_factory=lambda: list(DEFAULT_DIAG_ROLES))


class ClassifierTestRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class ClassifierTestResult(BaseModel):
    category: str
    confidence: float
    cached: bool
    reason: str | None = None


# ── Trace response ───────────────────────────────────────────────

class OrchestratorTraceResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    conversation_id: uuid.UUID | None
    user_id: uuid.UUID | None
    user_message: str
    metadata_snapshot: dict | None
    matched_rule_id: uuid.UUID | None
    match_type_used: str | None
    match_latency_ms: int | None
    llm_classifier_category: str | None
    llm_classifier_confidence: float | None
    llm_classifier_cached: bool
    handler_type: str | None
    handler_id: uuid.UUID | None
    handler_latency_ms: int | None
    handler_status: str | None
    tried_rules: list | None
    ab_group: str | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleMetrics(BaseModel):
    rule_id: uuid.UUID
    hit_count: int
    last_hit_at: datetime | None
    avg_latency_ms: int | None


# ── helpers ──────────────────────────────────────────────────────

def _flags_to_re(flags: str) -> int:
    import re as _re
    out = 0
    for ch in flags:
        out |= {"i": _re.IGNORECASE, "m": _re.MULTILINE, "s": _re.DOTALL}[ch]
    return out
