import { useCallback, useEffect, useState } from "react"
import { RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { systemApi, type HealthResponse, type ServiceHealth } from "@/api/system"

const statusColor: Record<ServiceHealth["status"], string> = {
  healthy: "bg-green-500",
  degraded: "bg-yellow-500",
  down: "bg-red-500",
}

const statusLabel: Record<ServiceHealth["status"], string> = {
  healthy: "正常",
  degraded: "降级",
  down: "离线",
}

export default function SystemPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await systemApi.health()
      setHealth(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <LoadingSpinner className="py-16" />

  if (!health) return null

  const uptimeHours = Math.floor(health.uptime_seconds / 3600)
  const uptimeMinutes = Math.floor((health.uptime_seconds % 3600) / 60)

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">系统状态</h2>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            运行时间: {uptimeHours}h {uptimeMinutes}m
          </span>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="mr-1 size-3.5" />
            刷新
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {health.services.map((svc) => (
          <Card key={svc.name} size="sm">
            <CardHeader>
              <div className="flex items-center gap-2">
                <span className={`inline-block h-2 w-2 rounded-full ${statusColor[svc.status]}`} />
                <CardTitle>{svc.name}</CardTitle>
                <Badge variant={svc.status === "healthy" ? "default" : "destructive"} className="ml-auto">
                  {statusLabel[svc.status]}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                {svc.latency_ms !== undefined && <span>延迟: {svc.latency_ms}ms</span>}
                {svc.message && <span>{svc.message}</span>}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
