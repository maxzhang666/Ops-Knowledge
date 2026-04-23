import { useEffect, useRef, useState } from "react"
import {
  Panel, PanelGroup, PanelResizeHandle,
  type ImperativePanelHandle,
} from "react-resizable-panels"
import { toast } from "sonner"
import { ChevronLeft, ChevronRight, GitBranch, MessageSquare } from "lucide-react"
import { Button } from "@/components/ui/button"
import { workflowApi, type NodeCatalogEntry } from "@/api/workflow"
import { Canvas } from "./canvas"
import { CanvasDrawer } from "./canvas-drawer"
import { ConfigPanel } from "./config-panel"
import { NodePalette } from "./node-palette"
import { SaveAsTemplateDialog } from "./drawers/templates"
import { WebhookDrawer } from "./drawers/webhook"
import { TestChatDrawer } from "./test-chat-drawer"
import { ProcessDrawer } from "./process-drawer"
import { VersionTimelineDrawer } from "./version-timeline-drawer"
import { useEditorStore } from "./store"
import { flowToGraph, graphToFlow, type RawGraph } from "./dsl"


export function WorkflowEditor({
  workflowId,
  embedded = false,
}: {
  workflowId: string
  embedded?: boolean
}) {
  const workflow = useEditorStore((s) => s.workflow)
  const nodes = useEditorStore((s) => s.nodes)
  const edges = useEditorStore((s) => s.edges)
  const selected = useEditorStore((s) => s.selected)
  const catalog = useEditorStore((s) => s.catalog)
  const setCatalog = useEditorStore((s) => s.setCatalog)
  const dirty = useEditorStore((s) => s.dirty)
  const setWorkflow = useEditorStore((s) => s.setWorkflow)
  const setNodes = useEditorStore((s) => s.setNodes)
  const setEdges = useEditorStore((s) => s.setEdges)
  const markClean = useEditorStore((s) => s.markClean)

  const [saving, setSaving] = useState(false)
  const [paletteCollapsed, setPaletteCollapsed] = useState(false)

  // 三个抽屉各自独立开关，互不冲突。test / versions 并排共存；
  // process 由 test 抽屉内的「过程」按钮触发，作为次级抽屉。
  const [testOpen, setTestOpen] = useState(false)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [processExecutionId, setProcessExecutionId] = useState<string | null>(null)

  const paletteRef = useRef<ImperativePanelHandle | null>(null)

  useEffect(() => {
    workflowApi.get(workflowId).then((wf) => {
      setWorkflow(wf)
      const flat = graphToFlow(wf.graph_data as RawGraph | null | undefined)
      setNodes(flat.nodes)
      setEdges(flat.edges)
      markClean()
    })
  }, [workflowId, setWorkflow, setNodes, setEdges, markClean])

  // 编辑器挂载时预加载节点 catalog（manifest 含 category / io 等元数据），
  // ProcessDrawer / ConfigPanel 等依赖它做判断，不再等 NodePalette 触发。
  useEffect(() => {
    if (catalog.length > 0) return
    workflowApi.nodeRegistry(false).then((res) => {
      if ("nodes" in res) setCatalog(res.nodes as NodeCatalogEntry[])
    })
  }, [catalog.length, setCatalog])

  useEffect(() => {
    if (!dirty) return
    function beforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault()
      e.returnValue = ""
    }
    window.addEventListener("beforeunload", beforeUnload)
    return () => window.removeEventListener("beforeunload", beforeUnload)
  }, [dirty])

  useEffect(() => {
    const p = paletteRef.current
    if (!p) return
    if (paletteCollapsed && !p.isCollapsed()) p.collapse()
    else if (!paletteCollapsed && p.isCollapsed()) p.expand()
  }, [paletteCollapsed])

  async function handleSave() {
    if (!workflow) return
    setSaving(true)
    try {
      const graph = flowToGraph(nodes, edges)
      const res = await workflowApi.update(workflow.id, {
        graph_data: graph as unknown as Record<string, unknown>,
      })
      setWorkflow(res)
      markClean()
      toast.success("已保存草稿")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  async function handlePublish() {
    if (!workflow) return
    if (dirty) await handleSave()
    try {
      const res = await workflowApi.publish(workflow.id)
      setWorkflow(res)
      toast.success(`已发布 v${res.version}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "发布失败")
    }
  }

  if (!workflow) return null

  // 选中节点且确有可配置字段（schema.properties 或 io.inputs）才显示配置面板。
  // 便签节点 / 无 schema 的节点选中时也不再打开 —— 避免弹出"此节点无可配置项"的空面板。
  const selectedNode = selected ? nodes.find((n) => n.id === selected) : null
  const selectedType = (selectedNode?.data as { nodeType?: string } | undefined)?.nodeType
  const showConfig = !!selectedType && hasConfigurableFields(selectedType, catalog)

  return (
    <div
      className={
        embedded
          ? "flex h-full w-full min-w-0 flex-1 flex-col"
          : "flex h-[calc(100vh-3.5rem)] w-full flex-col"
      }
    >
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{workflow.name}</div>
          <div className="text-xs text-muted-foreground">
            {workflow.status === "published" ? `v${workflow.version} 已发布` : "草稿"}
            {dirty && " · 未保存"}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={testOpen ? "default" : "outline"}
            onClick={() => setTestOpen((x) => !x)}
          >
            <MessageSquare className="mr-1 size-3.5" /> 测试
          </Button>
          <Button
            size="sm"
            variant={versionsOpen ? "default" : "outline"}
            onClick={() => setVersionsOpen((x) => !x)}
          >
            <GitBranch className="mr-1 size-3.5" /> 版本
          </Button>
          <WebhookDrawer />
          <SaveAsTemplateDialog />
          <Button
            variant="outline"
            size="sm"
            onClick={handleSave}
            disabled={saving || !dirty}
          >
            保存
          </Button>
          <Button size="sm" onClick={handlePublish} disabled={saving}>
            发布
          </Button>
        </div>
      </div>

      {/* 外层 flex row：左侧是 palette + canvas 的 PanelGroup（画布占满剩余空间）；
          右侧四个抽屉全部浮在画布上（absolute），不挤压画布宽度。
          配置面板（ConfigPanel）与三个功能抽屉同属浮层，区别仅是不带动画。 */}
      <div className="relative flex min-h-0 flex-1">
        <PanelGroup direction="horizontal" className="min-w-0 flex-1">
          <Panel
            ref={paletteRef}
            defaultSize={10}
            minSize={8}
            maxSize={20}
            collapsible
            collapsedSize={0}
            onCollapse={() => setPaletteCollapsed(true)}
            onExpand={() => setPaletteCollapsed(false)}
          >
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b px-2 py-1.5 text-xs font-medium">
                <span>节点</span>
                <button
                  type="button"
                  onClick={() => setPaletteCollapsed(true)}
                  className="inline-flex size-5 items-center justify-center rounded hover:bg-muted"
                  title="收起"
                >
                  <ChevronLeft className="size-3.5" />
                </button>
              </div>
              <div className="min-h-0 flex-1">
                <NodePalette />
              </div>
            </div>
          </Panel>

          {paletteCollapsed && (
            <button
              type="button"
              onClick={() => setPaletteCollapsed(false)}
              className="flex h-full w-5 items-center justify-center border-r bg-muted/40 hover:bg-muted"
              title="展开节点面板"
            >
              <ChevronRight className="size-3.5" />
            </button>
          )}

          <PanelResizeHandle className="w-px bg-border" />

          <Panel minSize={30}>
            <Canvas />
          </Panel>
        </PanelGroup>

        {/* 右侧浮层抽屉容器 — 从右至左顺序：配置面板｜版本｜测试｜过程。
            容器本身 pointer-events-none（不拦截画布操作），抽屉卡片
            在 open 状态下恢复 pointer-events-auto。 */}
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-stretch gap-2 py-2 pr-2">
          <CanvasDrawer open={!!processExecutionId} width={360}>
            {processExecutionId && (
              <ProcessDrawer
                executionId={processExecutionId}
                onClose={() => setProcessExecutionId(null)}
              />
            )}
          </CanvasDrawer>
          <CanvasDrawer open={testOpen} width={400}>
            <TestChatDrawer
              onClose={() => setTestOpen(false)}
              onOpenProcess={(id) => setProcessExecutionId(id)}
            />
          </CanvasDrawer>
          <CanvasDrawer open={versionsOpen} width={360}>
            <VersionTimelineDrawer onClose={() => setVersionsOpen(false)} />
          </CanvasDrawer>
          {/* 配置面板：固定 340px 最小宽度避免文字变形；无动画。 */}
          <CanvasDrawer open={showConfig} width={340} animated={false}>
            <ConfigPanel />
          </CanvasDrawer>
        </div>
      </div>
    </div>
  )
}


/** 判断某个节点类型在 catalog 中是否声明了任何可配置项。 */
function hasConfigurableFields(
  nodeType: string,
  catalog: Array<{
    manifest: { type: string }
    io?: { inputs?: Record<string, unknown> }
    config_form?: { schema?: unknown }
  }>,
): boolean {
  const entry = catalog.find((c) => c.manifest.type === nodeType)
  if (!entry) return false
  const schema = (entry.config_form?.schema as { properties?: Record<string, unknown> } | undefined) ?? {}
  const propCount = Object.keys(schema.properties ?? {}).length
  const inputCount = Object.keys(entry.io?.inputs ?? {}).length
  return propCount > 0 || inputCount > 0
}
