import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import {
  Bell, CheckCheck, ChevronLeft, ChevronRight, ExternalLink, RefreshCw,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { TimeDisplay } from "@/components/shared/time-display"
import { cn } from "@/lib/utils"
import {
  notificationApi,
  resolveNotificationLink,
  type Notification,
} from "@/api/notification"
import { useNotificationStore } from "@/stores/notification"

const PAGE_SIZE = 20

function priorityChip(priority: Notification["priority"]) {
  if (priority === "high") return <Badge variant="destructive">高</Badge>
  if (priority === "low") return <Badge variant="secondary">低</Badge>
  return <Badge variant="info">常规</Badge>
}

export default function NotificationsPage() {
  const navigate = useNavigate()
  const markAllRead = useNotificationStore((s) => s.markAllRead)
  const loadUnreadCount = useNotificationStore((s) => s.loadUnreadCount)

  const [items, setItems] = useState<Notification[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [filterType, setFilterType] = useState<string>("")
  const [filterRead, setFilterRead] = useState<"all" | "unread" | "read">("all")

  const fetchPage = useCallback(async () => {
    setLoading(true)
    try {
      const params: Parameters<typeof notificationApi.list>[0] = {
        page, page_size: PAGE_SIZE,
      }
      if (filterType) params.type = filterType
      if (filterRead === "unread") params.is_read = false
      if (filterRead === "read") params.is_read = true
      const res = await notificationApi.list(params)
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [page, filterType, filterRead])

  useEffect(() => {
    fetchPage()
  }, [fetchPage])

  // 已经出现过的 type 集合（用于 select 选项；避免硬编码）
  const typeOptions = useMemo(() => {
    const s = new Set<string>()
    items.forEach((n) => s.add(n.type))
    return Array.from(s).sort()
  }, [items])

  async function handleRowClick(n: Notification) {
    const link = resolveNotificationLink(n)
    if (!n.is_read) {
      try {
        await notificationApi.markRead(n.id)
        setItems((prev) =>
          prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)),
        )
        loadUnreadCount()
      } catch {
        // 静默
      }
    }
    if (link) navigate(link)
  }

  async function handleMarkAll() {
    try {
      await markAllRead()
      setItems((prev) => prev.map((n) => ({ ...n, is_read: true })))
      toast.success("已全部标记为已读")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "操作失败")
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <Bell className="size-5" />
            通知中心
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            系统通知历史 / 筛选 / 跳转关联资源；待审项请到{" "}
            <button
              type="button"
              onClick={() => navigate("/review")}
              className="text-info underline-offset-2 hover:underline"
            >
              审核中心
            </button>
            {" "}处理，队列异常请到{" "}
            <button
              type="button"
              onClick={() => navigate("/settings/task-failures")}
              className="text-info underline-offset-2 hover:underline"
            >
              队列治理
            </button>
            {" "}处理。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchPage} disabled={loading}>
            <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} />
            <span className="ml-1">刷新</span>
          </Button>
          <Button variant="outline" size="sm" onClick={handleMarkAll}>
            <CheckCheck className="size-4" />
            <span className="ml-1">全部已读</span>
          </Button>
        </div>
      </header>

      <div className="flex items-center gap-2">
        <select
          value={filterRead}
          onChange={(e) => {
            setFilterRead(e.target.value as "all" | "unread" | "read")
            setPage(1)
          }}
          className="h-9 rounded-md border bg-background px-3 text-sm"
        >
          <option value="all">全部状态</option>
          <option value="unread">未读</option>
          <option value="read">已读</option>
        </select>
        <select
          value={filterType}
          onChange={(e) => {
            setFilterType(e.target.value)
            setPage(1)
          }}
          className="h-9 rounded-md border bg-background px-3 text-sm"
        >
          <option value="">全部类型</option>
          {typeOptions.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <span className="ml-auto text-sm text-muted-foreground tabular-nums">
          共 {total} 条
        </span>
      </div>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 w-1" />
              <th className="px-3 py-2">通知</th>
              <th className="px-3 py-2 w-24">类型</th>
              <th className="px-3 py-2 w-16">优先级</th>
              <th className="px-3 py-2 w-32">时间</th>
              <th className="px-3 py-2 w-1" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  加载中...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  暂无通知
                </td>
              </tr>
            ) : (
              items.map((n) => {
                const link = resolveNotificationLink(n)
                return (
                  <tr
                    key={n.id}
                    className={cn(
                      "cursor-pointer border-b last:border-0 hover:bg-muted/30",
                      !n.is_read && "bg-info/[0.03]",
                    )}
                    onClick={() => handleRowClick(n)}
                  >
                    <td className="px-3 py-2">
                      {!n.is_read && (
                        <span className="block size-2 rounded-full bg-primary" title="未读" />
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <div className={cn("text-sm", !n.is_read && "font-medium")}>
                        {n.title}
                      </div>
                      {n.content && (
                        <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                          {n.content}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {n.type}
                      </Badge>
                    </td>
                    <td className="px-3 py-2">{priorityChip(n.priority)}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      <TimeDisplay value={n.created_at} />
                    </td>
                    <td className="px-3 py-2">
                      {link && (
                        <ExternalLink className="size-3.5 text-muted-foreground" />
                      )}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-end gap-2">
        <span className="text-xs text-muted-foreground tabular-nums">
          {page} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="icon"
          className="size-8"
          disabled={page <= 1 || loading}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          <ChevronLeft className="size-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="size-8"
          disabled={page >= totalPages || loading}
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  )
}
