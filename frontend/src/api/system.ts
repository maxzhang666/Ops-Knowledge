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

  // Plan 28 — Cost dashboard
  costSummary(windowDays = 30) {
    return api.get<{
      total_cost: number
      total_input_tokens: number
      total_output_tokens: number
      call_count: number
      window_days: number
    }>("/system/costs/summary", { window_days: String(windowDays) })
  },
  costTimeline(windowDays = 7) {
    return api.get<{
      window_days: number
      points: Array<{ date: string; cost: number; tokens: number; calls: number }>
    }>("/system/costs/timeline", { window_days: String(windowDays) })
  },
  costTop(by: "user" | "provider" | "model" | "call_type", windowDays = 30, limit = 10) {
    return api.get<{
      by: string
      window_days: number
      items: Array<{ key: string; label: string; cost: number; tokens: number; calls: number }>
    }>("/system/costs/top", { by, window_days: String(windowDays), limit: String(limit) })
  },
}
