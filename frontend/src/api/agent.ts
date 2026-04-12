import { api } from "./client"
import type { PaginatedResponse } from "./types"

export type AgentType = "simple" | "rag" | "workflow"

export interface Agent {
  id: string
  name: string
  description: string
  avatar: string
  agent_type: AgentType
  knowledge_base_ids: string[]
  model_provider_id: string
  model_name: string
  system_prompt: string
  welcome_message: string
  enable_thinking: boolean
  is_public: boolean
  created_at: string
  updated_at: string
}

interface CreateAgentPayload {
  name: string
  description?: string
  agent_type?: AgentType
}

interface UpdateAgentPayload {
  name?: string
  description?: string
  avatar?: string
  agent_type?: AgentType
  knowledge_base_ids?: string[]
  model_provider_id?: string
  model_name?: string
  system_prompt?: string
  welcome_message?: string
  enable_thinking?: boolean
  is_public?: boolean
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
    return api.patch<Agent>(`/agents/${id}`, data)
  },

  delete(id: string) {
    return api.delete<void>(`/agents/${id}`)
  },
}
