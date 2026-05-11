import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { ShieldCheck } from "lucide-react"

import { Button } from "@/components/ui/button"
import { reviewApi } from "@/api/review"

const POLL_INTERVAL_MS = 60_000

/** Plan 39 M3 — 全局审核徽章。
 * 60s 轮询 /review/pending/count，count > 0 显示数字徽章。
 * 后端按用户角色决定可见集（普通 user 永远 0，所以徽章不会显示）。 */
export function ReviewBadge() {
  const navigate = useNavigate()
  const [count, setCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const tick = async () => {
      try {
        const r = await reviewApi.pendingCount()
        if (!cancelled) setCount(r.count)
      } catch {
        // 静默重试，不弹 toast 避免轮询失败刷屏
      } finally {
        if (!cancelled) timer = setTimeout(tick, POLL_INTERVAL_MS)
      }
    }
    tick()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  if (count === 0) return null

  return (
    <Button
      variant="ghost"
      size="icon"
      className="relative"
      title={`待审 ${count} 项`}
      onClick={() => navigate("/review")}
    >
      <ShieldCheck className="h-4 w-4" />
      <span
        className="absolute -right-0.5 -top-0.5 inline-flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium leading-4 text-destructive-foreground"
      >
        {count > 99 ? "99+" : count}
      </span>
    </Button>
  )
}
