import { api } from "./client"
import type { PaginatedResponse } from "./types"

export interface Notification {
  id: string
  type: string
  title: string
  content: string | null
  priority: "low" | "normal" | "high"
  is_read: boolean
  resource_type: string | null
  resource_id: string | null
  created_at: string
}

export interface NotificationListParams {
  is_read?: boolean
  type?: string
  page?: number
  page_size?: number
}

// Only map to routes that actually exist in the frontend router (see router.tsx).
// Notifications for documents use resource_type="knowledge_base" now — the KB
// detail page is the real destination (document-level page does not exist).
// Conversations always live inside an Agent, so the backend must include
// agent_id in resource_id if it ever wants to deep-link — until then, omitted.
const RESOURCE_ROUTE: Record<string, (id: string) => string> = {
  knowledge_base: (id) => `/knowledge/${id}`,
  agent: (id) => `/agents/${id}`,
}

export function resolveNotificationLink(n: Notification): string | undefined {
  if (!n.resource_type || !n.resource_id) return undefined
  const builder = RESOURCE_ROUTE[n.resource_type]
  return builder ? builder(n.resource_id) : undefined
}

export interface UnreadCountResponse {
  count: number
}

export const notificationApi = {
  list(params: NotificationListParams = {}): Promise<PaginatedResponse<Notification>> {
    const qs = new URLSearchParams()
    if (params.is_read !== undefined) qs.set("is_read", String(params.is_read))
    if (params.type) qs.set("type", params.type)
    if (params.page !== undefined) qs.set("page", String(params.page))
    if (params.page_size !== undefined) qs.set("page_size", String(params.page_size))
    const q = qs.toString()
    return api.get<PaginatedResponse<Notification>>(`/notifications${q ? `?${q}` : ""}`)
  },

  unreadCount() {
    return api.get<UnreadCountResponse>("/notifications/unread-count")
  },

  markRead(id: string) {
    return api.post<void>(`/notifications/${id}/read`)
  },

  markAllRead() {
    return api.post<void>("/notifications/read-all")
  },
}
