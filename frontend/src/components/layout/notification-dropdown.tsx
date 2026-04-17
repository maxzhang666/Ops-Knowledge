import { useEffect, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { Bell, CheckCheck } from "lucide-react"
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
import { cn } from "@/lib/utils"

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
        {notifications.length === 0 ? (
          <div className="px-3 py-6 text-center text-sm text-muted-foreground">暂无通知</div>
        ) : (
          notifications.slice(0, 10).map((n) => (
            <DropdownMenuItem
              key={n.id}
              className="flex flex-col items-start gap-0.5 py-2"
              onClick={() => handleClick(n.id, resolveNotificationLink(n))}
            >
              <div className="flex w-full items-center gap-2">
                {!n.is_read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
                <span className={cn("flex-1 truncate text-sm", !n.is_read && "font-medium")}>{n.title}</span>
              </div>
              {n.content && (
                <p className="line-clamp-1 w-full text-xs text-muted-foreground">{n.content}</p>
              )}
              <span className="text-[10px] text-muted-foreground">
                <TimeDisplay value={n.created_at} />
              </span>
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
