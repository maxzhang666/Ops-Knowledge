import { useEffect, useState } from "react"
import { X, GitBranch, RotateCcw } from "lucide-react"
import { Timeline } from "@douyinfe/semi-ui"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { workflowApi } from "@/api/workflow"
import { useEditorStore } from "./store"
import { graphToFlow, type RawGraph } from "./dsl"


interface VersionRow {
  version: number
  published_at: string
  published_by: string | null
  change_note: string | null
}


/**
 * 版本历史 — Semi `<Timeline />`，每个 Item 的 content 是一张紧凑卡片：
 *   v 号（大）  | 相对时间 ·（发布者） | 回滚
 *   └── 可选备注（柔和背景色）
 * 当前已发布版本：success 类型（绿色图标）+ 卡片主色边框 + "当前" 徽标。
 */
export function VersionTimelineDrawer({ onClose }: { onClose: () => void }) {
  const workflow = useEditorStore((s) => s.workflow)
  const setWorkflow = useEditorStore((s) => s.setWorkflow)
  const setNodes = useEditorStore((s) => s.setNodes)
  const setEdges = useEditorStore((s) => s.setEdges)
  const markClean = useEditorStore((s) => s.markClean)

  const [versions, setVersions] = useState<VersionRow[]>([])
  const [loading, setLoading] = useState(false)

  const currentPublished = workflow?.status === "published" ? workflow.version : null

  useEffect(() => {
    if (!workflow) return
    setLoading(true)
    workflowApi.listVersions(workflow.id)
      .then((rows) => setVersions(rows))
      .finally(() => setLoading(false))
  }, [workflow])

  async function rollback(v: number) {
    if (!workflow) return
    if (!window.confirm(`将 v${v} 复制为当前草稿？当前未保存的改动会被覆盖。`)) return
    try {
      const res = await workflowApi.rollbackVersion(workflow.id, v)
      setWorkflow(res)
      const flat = graphToFlow(res.graph_data as RawGraph | null | undefined)
      setNodes(flat.nodes)
      setEdges(flat.edges)
      markClean()
      toast.success(`v${v} 已成为草稿`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "回滚失败")
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <GitBranch className="size-4" /> 版本历史
        </div>
        <Button variant="ghost" size="icon" className="size-7" onClick={onClose} title="关闭">
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {loading && <p className="text-xs text-muted-foreground">加载中...</p>}
        {!loading && versions.length === 0 && (
          <p className="text-xs text-muted-foreground">尚无历史版本。发布后会在这里出现。</p>
        )}
        {!loading && versions.length > 0 && (
          <Timeline mode="left">
            {versions.map((v) => {
              const isCurrent = v.version === currentPublished
              return (
                <Timeline.Item
                  key={v.version}
                  type={isCurrent ? "success" : "default"}
                >
                  <div
                    className={`rounded-md border bg-card px-3 py-2 text-xs transition-colors ${
                      isCurrent ? "border-primary/50 shadow-sm" : ""
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">v{v.version}</span>
                      {isCurrent && (
                        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                          当前
                        </span>
                      )}
                      <span className="ml-auto text-muted-foreground">
                        {formatTime(v.published_at)}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-[11px]"
                        onClick={() => rollback(v.version)}
                        title={`回滚到 v${v.version}`}
                      >
                        <RotateCcw className="mr-1 size-3" /> 回滚
                      </Button>
                    </div>
                    {v.change_note && (
                      <p className="mt-1.5 whitespace-pre-wrap rounded bg-muted/40 px-2 py-1 text-[11px] leading-relaxed text-muted-foreground">
                        {v.change_note}
                      </p>
                    )}
                  </div>
                </Timeline.Item>
              )
            })}
          </Timeline>
        )}
      </div>
    </div>
  )
}


function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    const now = Date.now()
    const diff = (now - d.getTime()) / 1000
    if (diff < 60) return `${Math.floor(diff)} 秒前`
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
    if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
    return d.toLocaleString()
  } catch {
    return iso
  }
}
