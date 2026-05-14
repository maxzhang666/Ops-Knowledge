import { api } from "./client"
import type { PaginatedResponse } from "./types"

// Spec 25 §6 — KB 字典治理（仅 KB owner / system_admin）

export interface TagDictItem {
  id: string
  canonical: string
  aliases: string[]
  usage_count: number
  is_deprecated: boolean
  created_at: string
  updated_at: string
}

export type TagDictOp =
  | "create" | "rename" | "merge" | "split" | "delete" | "set_aliases"

export interface TagDictAuditItem {
  id: string
  dict_id: string | null
  op: TagDictOp
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  affected_entries: number | null
  actor_id: string | null
  created_at: string
}

export interface ListTagsParams {
  search?: string
  include_deprecated?: boolean
  page?: number
  page_size?: number
}

export const tagDictionaryApi = {
  list: (kbId: string, params: ListTagsParams = {}): Promise<PaginatedResponse<TagDictItem>> => {
    const qs = new URLSearchParams()
    if (params.search) qs.set("search", params.search)
    if (params.include_deprecated) qs.set("include_deprecated", "true")
    if (params.page !== undefined) qs.set("page", String(params.page))
    if (params.page_size !== undefined) qs.set("page_size", String(params.page_size))
    const q = qs.toString()
    return api.get(`/knowledge/${kbId}/tag-dictionary${q ? `?${q}` : ""}`)
  },

  create: (kbId: string, body: { canonical: string; aliases?: string[] }): Promise<TagDictItem> =>
    api.post(`/knowledge/${kbId}/tag-dictionary`, body),

  setAliases: (kbId: string, dictId: string, aliases: string[]): Promise<TagDictItem> =>
    api.post(`/knowledge/${kbId}/tag-dictionary/${dictId}/aliases`, { aliases }),

  rename: (kbId: string, dictId: string, canonical: string): Promise<TagDictItem> =>
    api.post(`/knowledge/${kbId}/tag-dictionary/${dictId}/rename`, { canonical }),

  merge: (kbId: string, body: { source_ids: string[]; target_id: string }): Promise<TagDictItem> =>
    api.post(`/knowledge/${kbId}/tag-dictionary/merge`, body),

  softDelete: (kbId: string, dictId: string): Promise<TagDictItem> =>
    api.post(`/knowledge/${kbId}/tag-dictionary/${dictId}/delete`),

  listAudit: (kbId: string, page = 1, page_size = 50): Promise<PaginatedResponse<TagDictAuditItem>> => {
    const qs = new URLSearchParams({ page: String(page), page_size: String(page_size) })
    return api.get(`/knowledge/${kbId}/tag-dictionary/audit?${qs.toString()}`)
  },
}
