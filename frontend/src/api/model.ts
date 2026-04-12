import { api } from "./client"
import type { PaginatedResponse } from "./types"

export interface ModelProvider {
  id: string
  name: string
  provider_type: string
  api_base: string
  api_key_set: boolean
  models: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

interface CreateModelProviderPayload {
  name: string
  provider_type: string
  api_base: string
  api_key: string
  models?: string[]
}

interface UpdateModelProviderPayload {
  name?: string
  api_base?: string
  api_key?: string
  models?: string[]
  is_active?: boolean
}

interface TestResult {
  success: boolean
  message: string
  latency_ms?: number
}

export const modelApi = {
  list(params?: Record<string, string>) {
    return api.get<PaginatedResponse<ModelProvider>>("/model-providers", params)
  },

  get(id: string) {
    return api.get<ModelProvider>(`/model-providers/${id}`)
  },

  create(data: CreateModelProviderPayload) {
    return api.post<ModelProvider>("/model-providers", data)
  },

  update(id: string, data: UpdateModelProviderPayload) {
    return api.patch<ModelProvider>(`/model-providers/${id}`, data)
  },

  delete(id: string) {
    return api.delete<void>(`/model-providers/${id}`)
  },

  test(id: string) {
    return api.post<TestResult>(`/model-providers/${id}/test`)
  },
}
