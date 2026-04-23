/**
 * Orchestrator "SOP 流程" panel (Plan 31 N2.11).
 *
 * Owns a list of Workflows whose owner_agent_id == this Orchestrator. User
 * can:
 *   - see all SOPs under this Orchestrator
 *   - create a new Workflow (auto-bound to this agent)
 *   - pick one and edit its DAG in an embedded WorkflowEditor (right pane)
 *   - delete an unused SOP
 *
 * Two-pane layout (左列表 + 右编辑器) so the editing loop is "select → edit"
 * without navigating away.
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Plus, Trash2, FileCode2, Maximize2, Minimize2, PanelLeftClose, PanelLeftOpen,
} from "lucide-react"
import { toast } from "sonner"

import type { Agent } from "@/api/agent"
import { workflowApi, type WorkflowSummary } from "@/api/workflow"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { WorkflowEditor } from "@/features/workflow/editor"
import { cn } from "@/lib/utils"


interface WorkflowsPanelProps {
  agent: Agent
  onUpdated?: () => void
  /** Plan 31 N2.14 — 全屏模式下隐藏 Agent workbench 左栏（PreviewChat + Menu），
   * 给 WorkflowEditor 整屏宽度。由 AgentWorkbench 注入。 */
  fullscreen?: boolean
  onToggleFullscreen?: () => void
}

export function WorkflowsPanel({
  agent, onUpdated, fullscreen = false, onToggleFullscreen,
}: WorkflowsPanelProps) {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<WorkflowSummary | null>(null)
  // Plan 31 N2.14 — 左侧 SOP 列表折叠状态（组件本地，和 URL fullscreen 独立）
  const [listCollapsed, setListCollapsed] = useState(false)

  const [newName, setNewName] = useState("")
  const [newDesc, setNewDesc] = useState("")
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const rows = await workflowApi.list({ owner_agent_id: agent.id })
      setWorkflows(Array.isArray(rows) ? rows : [])
      setSelectedId((prev) => {
        if (prev && rows.some((w) => w.id === prev)) return prev
        return rows[0]?.id ?? null
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载 SOP 失败")
    } finally {
      setLoading(false)
    }
  }, [agent.id])

  useEffect(() => { load() }, [load])

  const defaultHandlerId = useMemo(() => {
    const cfg = (agent.orchestrator_config ?? {}) as Record<string, unknown>
    const dh = (cfg.default_handler as { handler_id?: string } | undefined) ?? {}
    return dh.handler_id ?? null
  }, [agent.orchestrator_config])

  async function handleCreate() {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const wf = await workflowApi.create({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        owner_agent_id: agent.id,
      })
      toast.success("SOP 已创建")
      setCreateOpen(false)
      setNewName("")
      setNewDesc("")
      await load()
      setSelectedId(wf.id)
      onUpdated?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "创建失败")
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await workflowApi.delete(deleteTarget.id)
      toast.success("SOP 已删除")
      setWorkflows((prev) => prev.filter((w) => w.id !== deleteTarget.id))
      if (selectedId === deleteTarget.id) {
        setSelectedId(null)
      }
      setDeleteTarget(null)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败")
    }
  }

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div className="flex h-full min-h-0 w-full flex-1">
      {/* 左侧：Workflow 列表（可折叠） */}
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r transition-[width] duration-200",
          listCollapsed ? "w-10" : "w-64",
        )}
      >
        <div className="flex items-center justify-between border-b px-2 py-2">
          {!listCollapsed && (
            <>
              <span className="text-sm font-semibold">SOP 流程</span>
              <div className="flex items-center gap-1">
                <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setCreateOpen(true)}>
                  <Plus className="mr-1 size-3" /> 新建
                </Button>
                <button
                  type="button"
                  onClick={() => setListCollapsed(true)}
                  className="inline-flex size-7 items-center justify-center rounded hover:bg-muted"
                  title="折叠列表"
                >
                  <PanelLeftClose className="size-3.5" />
                </button>
              </div>
            </>
          )}
          {listCollapsed && (
            <button
              type="button"
              onClick={() => setListCollapsed(false)}
              className="inline-flex size-7 items-center justify-center rounded hover:bg-muted"
              title="展开列表"
            >
              <PanelLeftOpen className="size-3.5" />
            </button>
          )}
        </div>
        {!listCollapsed && (
        <div className="flex-1 overflow-y-auto p-1">
          {workflows.length === 0 ? (
            <p className="p-4 text-center text-xs text-muted-foreground">
              暂无 SOP。点上方"新建"。
            </p>
          ) : (
            workflows.map((wf) => {
              const isSelected = selectedId === wf.id
              const isDefault = wf.id === defaultHandlerId
              return (
                <div
                  key={wf.id}
                  className={cn(
                    "group flex items-center gap-1.5 rounded px-2 py-1.5 text-xs",
                    isSelected ? "bg-primary/10" : "hover:bg-muted/50",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedId(wf.id)}
                    className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                  >
                    <FileCode2 className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{wf.name}</span>
                    {isDefault && (
                      <Badge variant="outline" className="shrink-0 text-[9px]">默认</Badge>
                    )}
                    {wf.status === "published" && (
                      <Badge variant="secondary" className="shrink-0 text-[9px]">已发布</Badge>
                    )}
                  </button>
                  <button
                    type="button"
                    className="invisible shrink-0 rounded p-0.5 hover:bg-destructive/10 group-hover:visible"
                    onClick={(e) => { e.stopPropagation(); setDeleteTarget(wf) }}
                    disabled={isDefault}
                    title={isDefault ? "默认 SOP 不能删除" : "删除"}
                  >
                    <Trash2 className={cn("size-3", isDefault && "opacity-30")} />
                  </button>
                </div>
              )
            })
          )}
        </div>
        )}
      </aside>

      {/* 右侧：WorkflowEditor（全屏按钮注入它自己的顶栏，不额外起一行） */}
      <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {selectedId ? (
          <WorkflowEditor
            workflowId={selectedId}
            embedded
            extraActions={onToggleFullscreen ? (
              <Button
                size="sm" variant="outline"
                onClick={onToggleFullscreen}
                title={fullscreen ? "退出全屏" : "全屏编辑（隐藏左侧预览 + 菜单）"}
              >
                {fullscreen ? <Minimize2 className="mr-1 size-3.5" /> : <Maximize2 className="mr-1 size-3.5" />}
                {fullscreen ? "退出全屏" : "全屏"}
              </Button>
            ) : undefined}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            选择左侧 SOP 开始编辑，或新建一个
          </div>
        )}
      </section>

      {/* 新建对话框 */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建 SOP 流程</DialogTitle>
            <DialogDescription>这个 SOP 属于当前编排智能体，可被规则派发使用</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <Label className="text-xs">名称 *</Label>
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="例：VPN 故障排查"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs">描述</Label>
              <Textarea
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                rows={3}
                placeholder="可选"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>取消</Button>
            <Button onClick={handleCreate} disabled={!newName.trim() || creating}>
              {creating ? "创建中..." : "创建并编辑"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除 SOP"
        description={`确认删除 "${deleteTarget?.name}"？规则表里指向该 SOP 的规则将失效。`}
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}
