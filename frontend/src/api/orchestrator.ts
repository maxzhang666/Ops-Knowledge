import { api } from "./client"

// ── Types ──────────────────────────────────────────────────────

export type MatchType = "condition" | "keyword" | "regex" | "llm_intent"
export type HandlerType = "simple_agent" | "workflow" | "mcp_tool" | "sub_agent"
export type OnHandlerError = "use_default" | "fallback_next" | "return_error"

export type ConditionOp = "==" | "!=" | "in" | "not_in" | ">" | "<" | ">=" | "<="

export interface ConditionMatchConfig {
  path: string
  op: ConditionOp
  value: string | number | boolean | Array<string | number>
}
export interface KeywordMatchConfig {
  any_of: string[]
  case_sensitive?: boolean
}
export interface RegexMatchConfig {
  pattern: string
  flags?: string
}
export interface LLMIntentMatchConfig {
  category: string
}

export interface AgentRule {
  id: string
  agent_id: string
  priority: number
  is_active: boolean
  version: number
  match_type: MatchType
  match_config: Record<string, unknown>
  handler_type: HandlerType
  handler_id: string | null
  handler_config: Record<string, unknown>
  on_handler_error: OnHandlerError
  hit_count: number
  last_hit_at: string | null
  avg_latency_ms: number | null
  created_at: string
  updated_at: string
}

export interface CreateRulePayload {
  priority?: number | null
  is_active?: boolean
  match_type: MatchType
  match_config: Record<string, unknown>
  handler_type: HandlerType
  handler_id?: string | null
  handler_config?: Record<string, unknown>
  on_handler_error?: OnHandlerError
}

export type UpdateRulePayload = Partial<CreateRulePayload>

export interface ClassifierCategory {
  name: string
  description?: string
  examples?: string[]
}

export interface ClassifierConfig {
  model_registry_id: string
  categories: ClassifierCategory[]
  confidence_threshold: number
  cache_ttl_seconds: number
  fallback_on_low_confidence: "default" | "next"
}

export interface DefaultHandler {
  handler_type: HandlerType
  handler_id?: string | null
  handler_config?: Record<string, unknown>
}

export interface OrchestratorConfig {
  classifier?: ClassifierConfig | null
  default_handler: DefaultHandler
  trusted_metadata_paths?: string[]
  diagnostic_mode_allowed_roles?: string[]
}

export interface ClassifierTestResult {
  category: string
  confidence: number
  cached: boolean
  reason?: string | null
}

export interface RuleMetrics {
  rule_id: string
  hit_count: number
  last_hit_at: string | null
  avg_latency_ms: number | null
}

export interface OrchestratorTrace {
  id: string
  agent_id: string
  conversation_id: string | null
  user_id: string | null
  user_message: string
  metadata_snapshot: Record<string, unknown> | null
  matched_rule_id: string | null
  match_type_used: string | null
  match_latency_ms: number | null
  llm_classifier_category: string | null
  llm_classifier_confidence: number | null
  llm_classifier_cached: boolean
  handler_type: string | null
  handler_id: string | null
  handler_latency_ms: number | null
  handler_status: string | null
  tried_rules: string[] | null
  ab_group: string | null
  error: string | null
  created_at: string
}

// ── API ────────────────────────────────────────────────────────

export const orchestratorApi = {
  listRules(agentId: string) {
    return api.get<AgentRule[]>(`/agents/${agentId}/rules`)
  },
  createRule(agentId: string, data: CreateRulePayload) {
    return api.post<AgentRule>(`/agents/${agentId}/rules`, data)
  },
  updateRule(agentId: string, ruleId: string, data: UpdateRulePayload) {
    return api.post<AgentRule>(`/agents/${agentId}/rules/${ruleId}/update`, data)
  },
  deleteRule(agentId: string, ruleId: string) {
    return api.post<void>(`/agents/${agentId}/rules/${ruleId}/delete`)
  },
  moveRule(agentId: string, ruleId: string, afterRuleId: string | null) {
    return api.post<AgentRule>(`/agents/${agentId}/rules/${ruleId}/move`, {
      after_rule_id: afterRuleId,
    })
  },
  metrics(agentId: string) {
    return api.get<RuleMetrics[]>(`/agents/${agentId}/rules/metrics`)
  },

  updateConfig(agentId: string, cfg: OrchestratorConfig) {
    return api.post<OrchestratorConfig>(
      `/agents/${agentId}/orchestrator-config/update`, cfg,
    )
  },
  testClassifier(agentId: string, message: string) {
    return api.post<ClassifierTestResult>(
      `/agents/${agentId}/classifier/test`, { message },
    )
  },

  listTraces(agentId: string, limit = 50) {
    return api.get<OrchestratorTrace[]>(`/agents/${agentId}/traces`, { limit: String(limit) })
  },
}
