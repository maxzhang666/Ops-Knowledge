import { useEffect, useState } from "react"
import { AlertTriangle, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { knowledgeApi } from "@/api/knowledge"

/**
 * 影响预览对话框（Plan 32 M3.5）—— 破坏性操作（删除/归档）前统一展示。
 *
 *   - 拉 `/documents/{id}/impact` 得到 chunk 数、7d 命中、活跃会话数、热门 chunk
 *   - 严重度配色：active_conversations>0 → destructive；hits>0 → warning；否则 default
 *   - action 按钮文案由调用方传入（"删除"/"归档"/"恢复"）
 */

interface ImpactPreviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  kbId: string
  docId: string
  docTitle: string
  action: "delete" | "archive" | "restore"
  onConfirm: () => Promise<void> | void
}

interface ImpactData {
  n_chunks: number
  hits_7d: number
  top_frequency_chunks: Array<{ chunk_id: string; preview: string; hits_7d: number }>
  active_conversations_7d: number
}

const ACTION_META: Record<ImpactPreviewDialogProps["action"], { title: string; confirm: string; destructive: boolean }> = {
  delete: { title: "删除文档", confirm: "确认删除", destructive: true },
  archive: { title: "归档文档", confirm: "确认归档", destructive: false },
  restore: { title: "恢复文档", confirm: "确认恢复", destructive: false },
}

export function ImpactPreviewDialog(props: ImpactPreviewDialogProps) {
  const { open, onOpenChange, kbId, docId, docTitle, action, onConfirm } = props
  const meta = ACTION_META[action]
  const [impact, setImpact] = useState<ImpactData | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open || action === "restore") {
      setImpact(null)
      return
    }
    let cancelled = false
    setLoading(true)
    knowledgeApi.documentImpact(kbId, docId)
      .then((d) => { if (!cancelled) setImpact(d) })
      .catch(() => { if (!cancelled) setImpact(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, kbId, docId, action])

  async function handleConfirm() {
    setSubmitting(true)
    try { await onConfirm() } finally { setSubmitting(false); onOpenChange(false) }
  }

  const hasImpact = (impact?.n_chunks ?? 0) > 0
    || (impact?.hits_7d ?? 0) > 0
    || (impact?.active_conversations_7d ?? 0) > 0
  const severe = (impact?.active_conversations_7d ?? 0) > 0

  return (
    <Dialog open={open} onOpenChange={(v) => !submitting && onOpenChange(v)}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{meta.title} · {docTitle}</DialogTitle>
          <DialogDescription>
            {action === "restore"
              ? "恢复后，下一次 lifecycle 扫描会重新评估新鲜度。"
              : "下面是该文档对当前知识库的影响面，操作后受影响的检索与会话如下。"}
          </DialogDescription>
        </DialogHeader>

        {action !== "restore" && (
          <div className="flex flex-col gap-3">
            {loading ? (
              <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> 正在分析影响…
              </div>
            ) : !impact ? (
              <div className="rounded-lg border p-4 text-sm text-muted-foreground">
                无法获取影响数据（可能是服务暂时不可用），你仍可执行操作。
              </div>
            ) : (
              <>
                <div className="grid grid-cols-3 gap-3">
                  <MetricCell label="切片数" value={impact.n_chunks} />
                  <MetricCell label="近 7 天命中" value={impact.hits_7d} />
                  <MetricCell
                    label="活跃会话 (7d)"
                    value={impact.active_conversations_7d}
                    severe={severe}
                  />
                </div>
                {severe && (
                  <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
                    <div>
                      近 7 天有 <b>{impact.active_conversations_7d}</b> 个会话引用过此文档的内容。
                      {action === "delete" ? "删除后相关引用将失效。" : "归档后新检索不会命中此文档。"}
                    </div>
                  </div>
                )}
                {impact.top_frequency_chunks.length > 0 && (
                  <div className="rounded-lg border">
                    <div className="border-b px-3 py-1.5 text-xs font-medium text-muted-foreground">
                      热门切片（按近 7 天命中次数）
                    </div>
                    <ul className="max-h-48 overflow-y-auto p-1">
                      {impact.top_frequency_chunks.map((c) => (
                        <li key={c.chunk_id} className="flex items-start gap-2 rounded px-2 py-1.5 text-xs">
                          <Badge variant="outline" className="shrink-0 font-mono">× {c.hits_7d}</Badge>
                          <span className="line-clamp-2 flex-1 text-muted-foreground">{c.preview || "—"}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {!hasImpact && (
                  <div className="rounded-lg border p-3 text-xs text-muted-foreground">
                    此文档近 7 天无检索命中，无引用会话。影响面较小。
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button
            variant={meta.destructive ? "destructive" : "default"}
            onClick={handleConfirm}
            disabled={submitting || loading}
          >
            {submitting ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : null}
            {meta.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MetricCell({ label, value, severe }: { label: string; value: number; severe?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border p-2.5">
      <p className={`text-xl font-semibold ${severe ? "text-destructive" : ""}`}>{value}</p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  )
}
