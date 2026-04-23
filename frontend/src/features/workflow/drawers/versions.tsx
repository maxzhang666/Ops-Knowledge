import { useEffect, useState } from "react"
import { History, RotateCcw } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { workflowApi } from "@/api/workflow"
import { useEditorStore } from "../store"
import { graphToFlow, type RawGraph } from "../dsl"

interface VersionRow {
  version: number
  published_at: string
  published_by: string | null
  change_note: string | null
}


export function VersionsDrawer() {
  const workflow = useEditorStore((s) => s.workflow)
  const setWorkflow = useEditorStore((s) => s.setWorkflow)
  const setNodes = useEditorStore((s) => s.setNodes)
  const setEdges = useEditorStore((s) => s.setEdges)
  const markClean = useEditorStore((s) => s.markClean)

  const [open, setOpen] = useState(false)
  const [versions, setVersions] = useState<VersionRow[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !workflow) return
    setLoading(true)
    workflowApi.listVersions(workflow.id)
      .then((rows) => setVersions(rows))
      .finally(() => setLoading(false))
  }, [open, workflow])

  async function rollback(v: number) {
    if (!workflow) return
    if (!window.confirm(`确定将 v${v} 回滚为草稿？当前草稿会被覆盖。`)) return
    try {
      const res = await workflowApi.rollbackVersion(workflow.id, v)
      setWorkflow(res)
      const flat = graphToFlow(res.graph_data as RawGraph | null | undefined)
      setNodes(flat.nodes)
      setEdges(flat.edges)
      markClean()
      toast.success(`已将 v${v} 复制为草稿`)
      setOpen(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "回滚失败")
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="outline" size="sm" />}>
        <History className="mr-1 size-3.5" /> 版本
      </SheetTrigger>
      <SheetContent className="w-96">
        <SheetHeader>
          <SheetTitle>版本历史</SheetTitle>
          <SheetDescription>最多保留 50 个已发布版本</SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-2">
          {loading && <p className="text-xs text-muted-foreground">加载中...</p>}
          {!loading && versions.length === 0 && (
            <p className="text-xs text-muted-foreground">暂无历史版本</p>
          )}
          {versions.map((v) => (
            <div
              key={v.version}
              className="flex items-start justify-between rounded-md border p-2 text-xs"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">v{v.version}</span>
                  <span className="text-muted-foreground">
                    {new Date(v.published_at).toLocaleString()}
                  </span>
                </div>
                {v.change_note && (
                  <div className="mt-1 text-muted-foreground">{v.change_note}</div>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-7"
                onClick={() => rollback(v.version)}
              >
                <RotateCcw className="mr-1 size-3" /> 回滚
              </Button>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}
