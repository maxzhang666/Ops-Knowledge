import { api } from "./client"

export interface ServiceHealth {
  name: string
  status: "healthy" | "degraded" | "down"
  latency_ms?: number
  message?: string
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "down"
  services: ServiceHealth[]
  uptime_seconds: number
}

export const systemApi = {
  health() {
    return api.get<HealthResponse>("/system/health")
  },
}
