import { useEffect, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { Bell, Check, CheckCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { TimeDisplay } from "@/components/shared/time-display"
import { useNotificationStore } from "@/stores/notification"
import { resolveNotificationLink } from "@/api/notification"

const POLL_INTERVAL = 30_000

export function NotificationDropdown() {
  const navigate = useNavigate()
  const unreadCount = useNotificationStore((s) => s.unreadCount)
  const notifications = useNotificationStore((s) => s.notifications)
  const loadUnreadCount = useNotificationStore((s) => s.loadUnreadCount)
  const loadNotifications = useNotificationStore((s) => s.loadNotifications)
  const markRead = useNotificationStore((s) => s.markRead)
  const markAllRead = useNotificationStore((s) => s.markAllRead)
  const timerRef = useRef<ReturnType<typeof setInterval>>(null)

  useEffect(() => {
    loadUnreadCount()
    timerRef.current = setInterval(loadUnreadCount, POLL_INTERVAL)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [loadUnreadCount])

  function handleOpen(open: boolean) {
    if (open) loadNotifications()
  }

  function handleClick(id: string, link?: string) {
    markRead(id)
    if (link) navigate(link)
  }

  return (
    <DropdownMenu onOpenChange={handleOpen}>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" title="通知" />}>
        <div className="relative">
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </div>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="flex items-center justify-between px-1.5">
          <DropdownMenuLabel>通知</DropdownMenuLabel>
          {unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-xs"
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                markAllRead()
              }}
            >
              <CheckCheck className="mr-1 size-3" />
              全部已读
            </Button>
          )}
        </div>
        <DropdownMenuSeparator />
        {(() => {
          // dropdown 仅展示未读：双保险（store 端 is_read=false 查；这里再次 filter
          // 防止 markRead 后 store 中 is_read=true 的项仍残留导致 stale 渲染）
          const unread = notifications.filter((n) => !n.is_read).slice(0, 10)
          if (unread.length === 0) {
            return (
              <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                暂无未读通知
              </div>
            )
          }
          return unread.map((n) => (
            <DropdownMenuItem
              key={n.id}
              className="group/notif flex items-start gap-2 py-2 pr-1.5"
              onClick={() => handleClick(n.id, resolveNotificationLink(n))}
            >
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              <div className="min-w-0 flex-1 space-y-0.5">
                <div className="truncate text-sm font-medium">{n.title}</div>
                {n.content && (
                  <p className="line-clamp-1 text-xs text-muted-foreground">{n.content}</p>
                )}
                <span className="text-[10px] text-muted-foreground">
                  <TimeDisplay value={n.created_at} />
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="size-6 shrink-0 opacity-60 hover:opacity-100"
                title="标记已读"
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  markRead(n.id)
                }}
              >
                <Check className="size-3.5" />
              </Button>
            </DropdownMenuItem>
          ))
        })()}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="justify-center text-xs text-muted-foreground"
          onClick={() => navigate("/notifications")}
        >
          查看全部通知 →
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
