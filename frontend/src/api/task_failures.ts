import { api } from "./client"
import type { PaginatedResponse } from "./types"

// Celery 任务失败追踪（system 域，仅 system_admin）

export type TaskFailureState = "FAILURE" | "UNREGISTERED" | "TIMEOUT"

export interface TaskFailureItem {
  id: string
  task_id: string | null
  task_name: string
  state: TaskFailureState
  exception: string | null
  retries: number
  kb_id: string | null
  actor_id: string | null
  failed_at: string
  retried_at: string | null
  resolved_at: string | null
}

export interface TaskFailureDetail extends TaskFailureItem {
  /** 触发任务的 args；UNREGISTERED 时可能是 {"_raw_b64": "..."} */
  args_json: unknown[] | Record<string, unknown> | null
  kwargs_json: Record<string, unknown> | null
  traceback: string | null
  enqueued_at: string | null
  resolved_by: string | null
}

export interface ListFailuresParams {
  page?: number
  page_size?: number
  state?: TaskFailureState
  task_name?: string
  kb_id?: string
  /** true=已处理 / false=未处理 / 省略=全部 */
  resolved?: boolean
}

export const taskFailuresApi = {
  list: (params: ListFailuresParams = {}): Promise<PaginatedResponse<TaskFailureItem>> => {
    const qs = new URLSearchParams()
    if (params.page !== undefined) qs.set("page", String(params.page))
    if (params.page_size !== undefined) qs.set("page_size", String(params.page_size))
    if (params.state) qs.set("state", params.state)
    if (params.task_name) qs.set("task_name", params.task_name)
    if (params.kb_id) qs.set("kb_id", params.kb_id)
    if (params.resolved !== undefined) qs.set("resolved", String(params.resolved))
    const q = qs.toString()
    return api.get(`/system/celery/failures${q ? `?${q}` : ""}`)
  },

  get: (id: string): Promise<TaskFailureDetail> =>
    api.get(`/system/celery/failures/${id}`),

  retry: (id: string): Promise<{ task_id: string; status: "accepted" }> =>
    api.post(`/system/celery/failures/${id}/retry`),

  resolve: (id: string): Promise<{ resolved_at: string }> =>
    api.post(`/system/celery/failures/${id}/resolve`),

  /** Header badge：最近 24h failed AND resolved_at IS NULL */
  pendingCount: (): Promise<{ count: number }> =>
    api.get("/system/celery/failures/pending/count"),

  /** #4 — 待向量化 chunk backlog (vector_id IS NULL 且 5min+) */
  vectorBacklog: (): Promise<{ count: number; age_seconds: number }> =>
    api.get("/system/celery/vector-backlog"),

  /** #4 — 手动触发 backlog 补偿（绕过 beat 5 分钟周期） */
  compensateVectorBacklog: (): Promise<{ task_id: string; status: "accepted" }> =>
    api.post("/system/celery/vector-backlog/compensate"),
}
