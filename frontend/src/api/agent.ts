import { api } from "./client"
import type { PaginatedResponse } from "./types"

export type AgentType = "simple" | "workflow" | "orchestrator"
export type ThinkingDetail = "minimal" | "normal"
export type NoResultMode = "honest" | "refuse" | "hybrid"

export interface Agent {
  id: string
  name: string
  description: string | null
  avatar: string | null
  agent_type: AgentType
  knowledge_base_ids: string[]
  folder_ids: string[]
  model_id: string | null
  model_provider_id: string | null
  model_name: string | null
  workflow_id: string | null
  system_prompt: string | null
  retrieval_config: Record<string, unknown> | null
  welcome_message: string | null
  show_thinking: boolean
  thinking_detail: string | null
  no_result_mode: string | null
  is_active: boolean
  share_to_dept: boolean
  created_by: string
  created_at: string
  updated_at: string
}

interface CreateAgentPayload {
  name: string
  description?: string
  avatar?: string
  agent_type?: AgentType
  knowledge_base_ids?: string[]
  folder_ids?: string[]
  model_id?: string
  model_provider_id?: string
  model_name?: string
  system_prompt?: string
  retrieval_config?: Record<string, unknown>
  welcome_message?: string
  show_thinking?: boolean
  thinking_detail?: string
  no_result_mode?: string
  share_to_dept?: boolean
}

interface UpdateAgentPayload {
  name?: string
  description?: string
  avatar?: string
  agent_type?: AgentType
  knowledge_base_ids?: string[]
  folder_ids?: string[]
  model_id?: string | null
  model_provider_id?: string | null
  model_name?: string | null
  workflow_id?: string | null
  system_prompt?: string
  retrieval_config?: Record<string, unknown> | null
  welcome_message?: string
  show_thinking?: boolean
  thinking_detail?: string | null
  no_result_mode?: string | null
  is_active?: boolean
  share_to_dept?: boolean
}

export interface PromptTemplate {
  id: string
  name: string
  description: string
  system_prompt: string
}

export interface PromptPreviewResponse {
  messages: Array<{ role: string; content: string }>
  detected_variables: string[]
  retrieval_will_trigger: boolean
}

export const agentApi = {
  list(params?: Record<string, string>) {
    return api.get<PaginatedResponse<Agent>>("/agents", params)
  },

  get(id: string) {
    return api.get<Agent>(`/agents/${id}`)
  },

  create(data: CreateAgentPayload) {
    return api.post<Agent>("/agents", data)
  },

  update(id: string, data: UpdateAgentPayload) {
    return api.post<Agent>(`/agents/${id}/update`, data)
  },

  delete(id: string) {
    return api.post<void>(`/agents/${id}/delete`)
  },

  listPromptTemplates() {
    return api.get<PromptTemplate[]>("/agents/prompt-templates")
  },

  previewPrompt(agentId: string, body: { query: string; system_prompt?: string }) {
    return api.post<PromptPreviewResponse>(`/agents/${agentId}/preview-prompt`, body)
  },
}
