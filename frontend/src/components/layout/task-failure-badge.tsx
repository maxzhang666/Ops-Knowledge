import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { AlertOctagon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { taskFailuresApi } from "@/api/task_failures"
import { useAuthStore } from "@/stores/auth"

const POLL_INTERVAL_MS = 30_000

/** Task Failure Badge — 30s 轮询最近 24h 未处理失败任务数。
 * 仅 system_admin 可见（前端 + 后端 require_role 双重校验）。 */
export function TaskFailureBadge() {
  const navigate = useNavigate()
  const role = useAuthStore((s) => s.user?.role)
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (role !== "system_admin") return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const tick = async () => {
      try {
        const r = await taskFailuresApi.pendingCount()
        if (!cancelled) setCount(r.count)
      } catch {
        // 静默重试
      } finally {
        if (!cancelled) timer = setTimeout(tick, POLL_INTERVAL_MS)
      }
    }
    tick()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [role])

  if (role !== "system_admin" || count === 0) return null

  return (
    <Button
      variant="ghost"
      size="icon"
      className="relative"
      title={`近 24h 队列异常 ${count} 条待处理`}
      onClick={() => navigate("/settings/task-failures")}
    >
      <AlertOctagon className="h-4 w-4" />
      <span className="absolute -right-0.5 -top-0.5 inline-flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium leading-4 text-destructive-foreground">
        {count > 99 ? "99+" : count}
      </span>
    </Button>
  )
}
