import { api } from "./client"
import type { PaginatedResponse } from "./types"

// Plan 39 M2 — 全局审核工作台

export type ReviewStatus = "pending" | "approved" | "rejected"
export type UnitType = "document" | "entry"

export interface ReviewItemView {
  unit_type: UnitType
  unit_id: string
  kb_id: string
  kb_name: string
  title: string
  /** 文件型独占：pdf / markdown / word / ...；条目型为 null */
  file_source_type: string | null
  chunk_count: number
  review_status: ReviewStatus
  review_comment: string | null
  submitted_by: string
  submitted_at: string
  reviewer_id: string | null
  reviewed_at: string | null
}

export interface ReviewDecisionResponse {
  document_id: string
  review_status: string
  reviewer_id: string | null
  reviewed_at: string | null
  review_comment: string | null
}

export interface PendingListFilters {
  page?: number
  page_size?: number
  kb_id?: string
  unit_type?: UnitType
}

export type HistoryMode = "reviewed_by_me" | "submitted_by_me"

export const reviewApi = {
  pendingCount: (): Promise<{ count: number }> =>
    api.get("/review/pending/count"),

  listPending: (filters: PendingListFilters = {}): Promise<PaginatedResponse<ReviewItemView>> => {
    const params = new URLSearchParams()
    if (filters.page) params.set("page", String(filters.page))
    if (filters.page_size) params.set("page_size", String(filters.page_size))
    if (filters.kb_id) params.set("kb_id", filters.kb_id)
    if (filters.unit_type) params.set("unit_type", filters.unit_type)
    const qs = params.toString()
    return api.get(`/review/pending${qs ? `?${qs}` : ""}`)
  },

  listHistory: (
    mode: HistoryMode,
    page = 1,
    page_size = 20,
  ): Promise<PaginatedResponse<ReviewItemView>> =>
    api.get(`/review/history?mode=${mode}&page=${page}&page_size=${page_size}`),

  approve: (
    unit_type: UnitType,
    unit_id: string,
    comment?: string,
  ): Promise<ReviewDecisionResponse> =>
    api.post(`/review/${unit_type}/${unit_id}/approve`, { comment: comment ?? null }),

  reject: (
    unit_type: UnitType,
    unit_id: string,
    comment: string,
  ): Promise<ReviewDecisionResponse> =>
    api.post(`/review/${unit_type}/${unit_id}/reject`, { comment }),

  comment: (
    unit_type: UnitType,
    unit_id: string,
    comment: string,
  ): Promise<ReviewDecisionResponse> =>
    api.post(`/review/${unit_type}/${unit_id}/comment`, { comment }),

  revert: (
    unit_type: UnitType,
    unit_id: string,
  ): Promise<ReviewDecisionResponse> =>
    api.post(`/review/${unit_type}/${unit_id}/revert`),
}
