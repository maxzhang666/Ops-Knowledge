import { useCallback, useEffect, useState } from "react"
import { Loader2 } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { TimeDisplay } from "@/components/shared/time-display"
import { knowledgeApi, type KnowledgeBase } from "@/api/knowledge"

/** Plan 29 M5 — KB 详情「审批」tab，列出待审批文档；点击跳到 documents tab。 */
export function ReviewTab({
  kb, onPick,
}: {
  kb: KnowledgeBase
  onPick: (docId: string) => void
}) {
  const [items, setItems] = useState<Array<{
    document_id: string
    title: string
    created_by: string
    created_at: string
    chunk_count: number
  }>>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await knowledgeApi.reviewQueue(kb.id)
      setItems(r.items)
    } finally {
      setLoading(false)
    }
  }, [kb.id])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> 加载中…
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <Card size="sm">
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          没有待审批文档
        </CardContent>
      </Card>
    )
  }

  return (
    <Card size="sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">待审批 ({items.length})</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-left text-xs font-medium text-muted-foreground">
                <th className="px-3 py-2">文档</th>
                <th className="px-3 py-2 text-right">分块数</th>
                <th className="px-3 py-2 text-right">提交时间</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr
                  key={row.document_id}
                  className="border-b last:border-b-0 cursor-pointer hover:bg-muted/30"
                  onClick={() => onPick(row.document_id)}
                >
                  <td className="px-3 py-2">
                    <span className="font-medium">{row.title}</span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Badge variant="outline" className="text-[10px]">{row.chunk_count}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right text-xs text-muted-foreground">
                    <TimeDisplay value={row.created_at} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">点击行打开文档详情，在右侧操作区进行审批</p>
      </CardContent>
    </Card>
  )
}
