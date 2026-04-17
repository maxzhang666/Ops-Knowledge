import { api } from "./client"

export interface HealthResponse {
  status: "ok" | "degraded"
  version: string
  services: Record<string, string>  // e.g. { postgres: "ok", redis: "ok", milvus: "unavailable" }
}

export interface TestConnectionResponse {
  service: string
  ok: boolean
  detail: string
}

export const systemApi = {
  health() {
    return api.get<HealthResponse>("/system/health")
  },
  getSettings() {
    return api.get<Record<string, unknown>>("/system/settings")
  },
  updateSettings(data: Record<string, unknown>) {
    return api.post<Record<string, unknown>>("/system/settings/update", data)
  },
  testConnection(service: string, config?: Record<string, unknown>) {
    return api.post<TestConnectionResponse>("/system/test-connection", { service, config })
  },
}
