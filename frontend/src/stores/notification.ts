import { create } from "zustand"
import { notificationApi, type Notification } from "@/api/notification"

interface NotificationState {
  unreadCount: number
  notifications: Notification[]
  loadUnreadCount: () => Promise<void>
  loadNotifications: () => Promise<void>
  markRead: (id: string) => Promise<void>
  markAllRead: () => Promise<void>
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  unreadCount: 0,
  notifications: [],

  async loadUnreadCount() {
    try {
      const res = await notificationApi.unreadCount()
      set({ unreadCount: res.count })
    } catch { /* silent */ }
  },

  async loadNotifications() {
    try {
      const res = await notificationApi.list({ page_size: "20" })
      const list = Array.isArray(res) ? res : (res as any).items ?? []
      set({ notifications: list })
    } catch { /* silent */ }
  },

  async markRead(id) {
    await notificationApi.markRead(id)
    set((s) => ({
      notifications: s.notifications.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
      unreadCount: Math.max(0, s.unreadCount - 1),
    }))
  },

  async markAllRead() {
    await notificationApi.markAllRead()
    const { notifications } = get()
    set({
      notifications: notifications.map((n) => ({ ...n, is_read: true })),
      unreadCount: 0,
    })
  },
}))
