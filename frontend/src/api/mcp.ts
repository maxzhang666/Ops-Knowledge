import { api } from "./client"

export type MCPTransportType = "http" | "sse" | "stdio"

export interface MCPServerBase {
  name: string
  description: string | null
  transport_type: MCPTransportType
  config: Record<string, unknown>
  auth_config: Record<string, unknown> | null
  enabled_tools: string[] | null
  is_active: boolean
}

export interface MCPServer extends MCPServerBase {
  id: string
  health_status: "ok" | "degraded" | "unreachable" | null
  last_checked_at: string | null
  discovered_tools: MCPTool[] | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface MCPTool {
  name: string
  description: string | null
  input_schema: Record<string, unknown> | null
}

export interface TestConnectionResult {
  ok: boolean
  detail: string
  server_info: {
    name: string | null
    version: string | null
    protocol_version: string | null
  } | null
}

export interface CreateMCPServerPayload {
  name: string
  description?: string | null
  transport_type: MCPTransportType
  config: Record<string, unknown>
  auth_config?: Record<string, unknown> | null
  enabled_tools?: string[] | null
  is_active?: boolean
}

export type UpdateMCPServerPayload = Partial<CreateMCPServerPayload>

export const mcpApi = {
  list(activeOnly = false) {
    return api.get<MCPServer[]>("/mcp/servers", activeOnly ? { active_only: "true" } : undefined)
  },
  get(id: string) {
    return api.get<MCPServer>(`/mcp/servers/${id}`)
  },
  create(data: CreateMCPServerPayload) {
    return api.post<MCPServer>("/mcp/servers", data)
  },
  update(id: string, data: UpdateMCPServerPayload) {
    return api.post<MCPServer>(`/mcp/servers/${id}/update`, data)
  },
  delete(id: string) {
    return api.post<void>(`/mcp/servers/${id}/delete`)
  },
  testConnection(id: string) {
    return api.post<TestConnectionResult>(`/mcp/servers/${id}/test-connection`)
  },
  discoverTools(id: string) {
    return api.post<MCPTool[]>(`/mcp/servers/${id}/discover-tools`)
  },
  getTools(id: string) {
    return api.get<MCPTool[]>(`/mcp/servers/${id}/tools`)
  },
}
