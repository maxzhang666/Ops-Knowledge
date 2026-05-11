import { api } from "./client"
import type { PaginatedResponse } from "./types"

// Plan 41 — 条目型 KB CRUD

export type EntryProcessingStatus = "pending" | "processing" | "completed" | "error"

export interface KnowledgeEntry {
  id: string
  knowledge_base_id: string
  folder_id: string | null
  title: string
  content: string
  tags: string[] | null
  token_count: number
  is_archived: boolean
  is_stale: boolean
  /** 处理状态：pending → processing → completed / error */
  status: EntryProcessingStatus
  error_message: string | null
  review_status: "pending" | "approved" | "rejected" | null
  review_comment: string | null
  created_by: string
  /** 编辑器信息面板使用：created_by 对应的 username */
  created_by_name: string | null
  reviewer_id: string | null
  reviewer_name: string | null
  reviewed_at: string | null
  created_at: string
  updated_at: string
}

export interface EntryCreatePayload {
  title: string
  content: string
  tags?: string[]
  folder_id?: string | null
}

export type EntryUpdatePayload = Partial<EntryCreatePayload>

export const entryApi = {
  create: (kb_id: string, payload: EntryCreatePayload): Promise<KnowledgeEntry> =>
    api.post(`/knowledge/${kb_id}/entries`, payload),

  list: (kb_id: string, page = 1, page_size = 50, folder_id?: string | null): Promise<PaginatedResponse<KnowledgeEntry>> => {
    const params = new URLSearchParams()
    params.set("page", String(page))
    params.set("page_size", String(page_size))
    if (folder_id) params.set("folder_id", folder_id)
    return api.get(`/knowledge/${kb_id}/entries?${params.toString()}`)
  },

  get: (kb_id: string, entry_id: string): Promise<KnowledgeEntry> =>
    api.get(`/knowledge/${kb_id}/entries/${entry_id}`),

  update: (
    kb_id: string,
    entry_id: string,
    payload: EntryUpdatePayload,
  ): Promise<KnowledgeEntry> =>
    api.post(`/knowledge/${kb_id}/entries/${entry_id}/update`, payload),

  delete: (kb_id: string, entry_id: string): Promise<void> =>
    api.post(`/knowledge/${kb_id}/entries/${entry_id}/delete`),

  importBatch: (kb_id: string, file: File): Promise<{ task_id: string; status: string }> => {
    const fd = new FormData()
    fd.append("file", file)
    return api.post(`/knowledge/${kb_id}/entries/import`, fd)
  },

  batchDelete: (kb_id: string, ids: string[]): Promise<{ status: string; deleted: number }> =>
    api.post(`/knowledge/${kb_id}/entries/batch/delete`, { ids }),

  batchArchive: (kb_id: string, ids: string[]): Promise<{ status: string; archived: number }> =>
    api.post(`/knowledge/${kb_id}/entries/batch/archive`, { ids }),
}
