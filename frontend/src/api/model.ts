import { api } from "./client"

export interface ModelsAvailable {
  llm: string[]
  embedding: string[]
  reranker: string[]
}

export interface ModelProvider {
  id: string
  name: string
  type: string
  base_url: string
  api_key: string | null
  extra_config: Record<string, unknown> | null
  models_available: ModelsAvailable
  default_llm_model: string | null
  default_embedding_model: string | null
  is_active: boolean
  created_by: string
  created_at: string
  updated_at: string
}

interface CreateModelProviderPayload {
  name: string
  type: string
  base_url?: string
  api_key?: string
  extra_config?: Record<string, unknown>
  models_available?: ModelsAvailable
  default_llm_model?: string
  default_embedding_model?: string
}

interface UpdateModelProviderPayload {
  name?: string
  type?: string
  base_url?: string
  api_key?: string
  extra_config?: Record<string, unknown>
  models_available?: ModelsAvailable
  default_llm_model?: string | null
  default_embedding_model?: string | null
  is_active?: boolean
}

export interface TestResult {
  llm: string
  llm_detail?: string
  embedding: string
  embedding_detail?: string
}

export interface RegistryEntry {
  id: string
  provider_id: string
  provider_name: string | null
  model_id: string
  display_name: string | null
  model_type: "llm" | "embedding" | "reranker"
  is_enabled: boolean
  created_at: string
}

export interface ProviderFieldSchema {
  name: string
  label?: string
  required: boolean
  type: "text" | "password" | "url" | "select"
  placeholder?: string
  default?: string
  options?: string[]
}

export interface ProviderTypeSchema {
  type: string
  label: string
  fields: ProviderFieldSchema[]
  capabilities: string[]
}

export const modelApi = {
  list(params?: Record<string, string>) {
    return api.get<ModelProvider[]>("/model", params)
  },

  get(id: string) {
    return api.get<ModelProvider>(`/model/${id}`)
  },

  create(data: CreateModelProviderPayload) {
    return api.post<ModelProvider>("/model", data)
  },

  update(id: string, data: UpdateModelProviderPayload) {
    return api.post<ModelProvider>(`/model/${id}/update`, data)
  },

  delete(id: string) {
    return api.post<void>(`/model/${id}/delete`)
  },

  test(id: string) {
    return api.post<TestResult>(`/model/${id}/test`)
  },

  discover(data: { type: string; base_url?: string; api_key?: string }) {
    return api.post<{ models: Array<{ id: string; type_hint: string }> }>("/model/discover", data)
  },

  createRegistryEntry(data: { provider_id: string; model_id: string; model_type: string; is_enabled?: boolean }) {
    return api.post<RegistryEntry>("/model/registry", data)
  },

  listRegistry(params?: Record<string, string>) {
    return api.get<RegistryEntry[]>("/model/registry", params)
  },

  updateRegistryEntry(id: string, data: { display_name?: string; model_type?: string; is_enabled?: boolean }) {
    return api.post<RegistryEntry>(`/model/registry/${id}/update`, data)
  },

  deleteRegistryEntry(id: string) {
    return api.post<void>(`/model/registry/${id}/delete`)
  },

  syncRegistry(providerId: string) {
    return api.post<{ synced: number }>(`/model/registry/sync/${providerId}`)
  },

  listProviderTypes() {
    return api.get<ProviderTypeSchema[]>("/model/provider-types")
  },
}
