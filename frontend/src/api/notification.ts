import { api } from "./client"
import type { PaginatedResponse } from "./types"

export interface Notification {
  id: string
  type: string
  title: string
  content: string
  is_read: boolean
  link?: string
  created_at: string
}

export interface UnreadCountResponse {
  count: number
}

export const notificationApi = {
  list(params?: Record<string, string>) {
    return api.get<PaginatedResponse<Notification>>("/notifications", params)
  },

  unreadCount() {
    return api.get<UnreadCountResponse>("/notifications/unread-count")
  },

  markRead(id: string) {
    return api.patch<void>(`/notifications/${id}/read`)
  },

  markAllRead() {
    return api.post<void>("/notifications/read-all")
  },
}
