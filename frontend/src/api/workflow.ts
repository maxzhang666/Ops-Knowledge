import { api } from "./client"

export interface WorkflowSummary {
  id: string
  name: string
  description: string | null
  version: number
  status: "draft" | "published"
  trigger_type: string
  owner_agent_id: string | null
  created_at: string
  updated_at: string
}

export interface WorkflowDetail extends WorkflowSummary {
  graph_data: unknown
  published_graph_data: unknown | null
  webhook_config: {
    hook_id?: string
    auth_type?: string
    allowed_ips?: string[]
  } | null
}

export interface NodeCatalogEntry {
  manifest: {
    type: string
    type_version: string
    category: string
    name: string
    description?: string
    streaming?: boolean
    is_terminal?: boolean
    is_compound?: boolean
  }
  io: {
    inputs: Record<string, unknown>
    outputs: Record<string, unknown>
  }
  config_form: {
    schema: unknown
    ui_schema: unknown
  }
}

export const workflowApi = {
  list(params?: { owner_agent_id?: string }) {
    const qs: Record<string, string> = {}
    if (params?.owner_agent_id) qs.owner_agent_id = params.owner_agent_id
    return api.get<WorkflowSummary[]>("/workflow", Object.keys(qs).length ? qs : undefined)
  },
  get(id: string) {
    return api.get<WorkflowDetail>(`/workflow/${id}`)
  },
  create(data: { name: string; description?: string; owner_agent_id?: string }) {
    return api.post<WorkflowDetail>("/workflow", data)
  },
  update(id: string, data: { name?: string; description?: string; graph_data?: unknown }) {
    return api.post<WorkflowDetail>(`/workflow/${id}/update`, data)
  },
  delete(id: string) {
    return api.post<void>(`/workflow/${id}/delete`)
  },
  publish(id: string, change_note?: string) {
    return api.post<WorkflowDetail>(`/workflow/${id}/publish`, { change_note })
  },
  revertDraft(id: string) {
    return api.post<WorkflowDetail>(`/workflow/${id}/draft`)
  },
  nodeRegistry(grouped = false) {
    const params = grouped ? { group: "true" } : undefined
    return api.get<
      | { nodes: NodeCatalogEntry[] }
      | { groups: Array<{ category: string; nodes: NodeCatalogEntry[] }> }
    >("/workflow/nodes/registry", params)
  },

  // ----- Execution lifecycle -----
  run(
    id: string,
    inputs: Record<string, unknown>,
    opts: { from_draft?: boolean } = {},
  ) {
    return api.post<{ execution_id: string }>(
      `/workflow/${id}/run`,
      { inputs, from_draft: opts.from_draft ?? false },
    )
  },
  listExecutions(id: string) {
    return api.get<Array<{
      id: string
      status: string
      started_at: string | null
      finished_at: string | null
      error: string | null
    }>>(`/workflow/${id}/executions`)
  },
  getExecution(id: string, execId: string) {
    return api.get<{
      id: string
      status: string
      output: Record<string, unknown> | null
      error: string | null
      started_at: string | null
      finished_at: string | null
      nodes: Array<{
        node_id: string
        type: string
        status: string
        input: Record<string, unknown> | null
        output: Record<string, unknown> | null
        error: string | null
      }>
    }>(`/workflow/${id}/executions/${execId}`)
  },
  cancelExecution(id: string, execId: string) {
    return api.post<{ ok: boolean; scheduler_reachable: boolean }>(
      `/workflow/${id}/executions/${execId}/cancel`,
    )
  },

  /** HITL resume — re-enter a waiting execution with a user-supplied value
   *  that's handed back to ``interrupt()`` inside the paused human_approval
   *  node. Server returns the same execution_id; client should re-subscribe
   *  the events WS to see continuation. */
  resumeExecution(id: string, execId: string, value: unknown) {
    return api.post<{ execution_id: string }>(
      `/workflow/${id}/executions/${execId}/resume`,
      { value },
    )
  },

  // ----- Versions -----
  listVersions(id: string) {
    return api.get<Array<{
      version: number
      published_at: string
      published_by: string | null
      change_note: string | null
    }>>(`/workflow/${id}/versions`)
  },
  getVersion(id: string, version: number) {
    return api.get<{
      version: number
      graph_data: Record<string, unknown>
      published_at: string
      change_note: string | null
    }>(`/workflow/${id}/versions/${version}`)
  },
  rollbackVersion(id: string, version: number) {
    return api.post<WorkflowDetail>(`/workflow/${id}/versions/${version}/rollback`)
  },

  // ----- Governance trigger -----
  listGovernanceHandlers() {
    return api.get<Array<{
      id: string
      name: string
      description: string | null
      trigger_type: string
      status: string
    }>>("/workflow", { trigger_type: "governance_event", wf_status: "published" })
  },

  // ----- Templates -----
  listTemplates(category?: string) {
    return api.get<Array<{
      id: string
      name: string
      description: string | null
      category: string
      is_builtin: boolean
      created_at: string
    }>>("/workflow/templates", category ? { category } : undefined)
  },
  getTemplate(tplId: string) {
    return api.get<{
      id: string
      name: string
      description: string | null
      category: string
      graph_data: Record<string, unknown>
      is_builtin: boolean
    }>(`/workflow/templates/${tplId}`)
  },
  saveAsTemplate(
    wfId: string,
    body: { name: string; description?: string; category?: string },
  ) {
    return api.post<{ id: string; name: string; category: string }>(
      `/workflow/${wfId}/save-as-template`, body,
    )
  },
  createFromTemplate(tplId: string, name: string) {
    return api.post<WorkflowDetail>(
      `/workflow/templates/${tplId}/create`, { name },
    )
  },
  deleteTemplate(tplId: string) {
    return api.post<{ ok: boolean }>(`/workflow/templates/${tplId}/delete`)
  },

  // ----- Webhook management -----
  regenerateWebhook(id: string, auth_type: "none" | "bearer" | "hmac") {
    return api.post<{
      hook_id: string
      auth_type: string
      secret?: string
      allowed_ips?: string[]
    }>(`/workflow/${id}/webhook/regenerate`, { auth_type })
  },
  updateWebhookConfig(
    id: string,
    patch: { auth_type?: string; allowed_ips?: string[] },
  ) {
    return api.post<Record<string, unknown>>(
      `/workflow/${id}/webhook/config/update`, patch,
    )
  },
  deleteWebhook(id: string) {
    return api.post<{ ok: boolean }>(`/workflow/${id}/webhook/delete`)
  },
}
