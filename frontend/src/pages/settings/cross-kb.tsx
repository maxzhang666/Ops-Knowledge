import { useEffect, useState } from "react"
import { Layers, Loader2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { knowledgeApi } from "@/api/knowledge"

/**
 * Plan 31 M3 — Admin 跨库重复 Top-N 视图。
 * 数据由 daily Celery `cross_kb_redundancy_scan` 产出。
 */
export default function CrossKBPage() {
  const [items, setItems] = useState<Array<{
    kb_a_id: string
    kb_a_name: string
    kb_b_id: string
    kb_b_name: string
    chunk_a_id: string
    chunk_b_id: string
    similarity: number
    a_preview: string
    b_preview: string
  }>>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    knowledgeApi.crossKbRedundancy(100, 0.85)
      .then((r) => { if (!cancelled) setItems(r.items) })
      .catch(() => { if (!cancelled) setItems([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">跨库治理</h1>
        <p className="text-xs text-muted-foreground">
          每日离线扫描产出的跨知识库高相似切片对（相似度 ≥ 0.85）
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> 加载中…
        </div>
      ) : items.length === 0 ? (
        <Card size="sm">
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            暂无跨库重复数据 —— 后台任务每日运行；如刚开启，请稍候
          </CardContent>
        </Card>
      ) : (
        <Card size="sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Layers className="size-4 text-primary" /> 跨库重复对 ({items.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {items.map((p, i) => (
              <div key={`${p.chunk_a_id}-${p.chunk_b_id}-${i}`} className="flex flex-col gap-1.5 rounded-md border p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs">
                    <Badge variant="outline">{p.kb_a_name}</Badge>
                    <span className="text-muted-foreground">↔</span>
                    <Badge variant="outline">{p.kb_b_name}</Badge>
                  </div>
                  <Badge variant="secondary" className="font-mono text-[10px]">
                    sim {p.similarity.toFixed(2)}
                  </Badge>
                </div>
                <div className="flex flex-col gap-1 text-[11px]">
                  <span className="line-clamp-2 text-muted-foreground">A · {p.a_preview || "—"}</span>
                  <span className="line-clamp-2 text-muted-foreground">B · {p.b_preview || "—"}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
