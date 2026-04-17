import { api } from "./client"

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
  list(params?: Record<string, string>) {
    return api.get<Notification[]>("/notifications", params)
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
