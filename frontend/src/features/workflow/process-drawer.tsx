import { useEffect, useState } from "react"
import { X, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { workflowApi } from "@/api/workflow"
import { OutputBlock } from "./debug/output-view"
import { useEditorStore } from "./store"
import { nodeNameCn } from "./i18n"


interface NodeDetail {
  node_id: string
  type: string
  status: string
  input: Record<string, unknown> | null
  output: Record<string, unknown> | null
  error: string | null
}


/**
 * Second-level drawer: shows the full per-node input+output trace for a
 * given execution. Opened by the "过程" button on an assistant bubble in
 * TestChatDrawer.
 *
 * Non-modal, Canvas-level (same Panel or overlay within the tester
 * container). User closes it with the X; doesn't auto-dismiss.
 */
interface Props {
  executionId: string
  onClose: () => void
}


export function ProcessDrawer({ executionId, onClose }: Props) {
  const workflow = useEditorStore((s) => s.workflow)
  const nodes = useEditorStore((s) => s.nodes)
  const edges = useEditorStore((s) => s.edges)
  const catalog = useEditorStore((s) => s.catalog)
  const [detail, setDetail] = useState<{
    status: string
    nodes: NodeDetail[]
    output: Record<string, unknown> | null
    error: string | null
    started_at: string | null
    finished_at: string | null
  } | null>(null)
  const [loading, setLoading] = useState(true)

  // 触发节点类型集合。优先从 catalog.manifest.category 推导；兜底硬编码
  // 已知 trigger 类型，避免 catalog 尚未加载时漏判（ProcessDrawer 常在
  // NodePalette 未展开的场景下被打开，那时 catalog 还是空的）。
  const triggerTypes = new Set<string>(["start"])
  for (const c of catalog) {
    if (c.manifest.category === "trigger") triggerTypes.add(c.manifest.type)
  }

  useEffect(() => {
    if (!workflow) return
    setLoading(true)
    workflowApi.getExecution(workflow.id, executionId)
      .then((d) => setDetail(d))
      .finally(() => setLoading(false))
  }, [workflow, executionId])

  // skipped 节点在后端 execution_service 持久化时就被过滤（N 选 1 的副产物），
  // 这里拿到的 detail.nodes 天然不含它们。
  const orderedNodes = orderByTopology(detail?.nodes ?? [], nodes, edges)

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="text-sm font-medium">生成过程</div>
        <Button
          variant="ghost"
          size="icon"
          className="size-7"
          onClick={onClose}
          title="关闭"
        >
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {loading && (
          <div className="flex items-center justify-center py-6 text-xs text-muted-foreground">
            <Loader2 className="mr-1 size-3.5 animate-spin" /> 加载中...
          </div>
        )}
        {!loading && !detail && (
          <p className="text-xs text-muted-foreground">找不到执行记录</p>
        )}
        {!loading && detail && (
          <>
            <ExecutionHeader detail={detail} />
            {orderedNodes.length === 0 ? (
              <p className="text-xs text-muted-foreground">本次执行无节点步骤</p>
            ) : (
              orderedNodes.map((n, idx) => (
                <NodeStep
                  key={n.node_id}
                  index={idx + 1}
                  node={n}
                  isTrigger={triggerTypes.has(n.type)}
                />
              ))
            )}
          </>
        )}
      </div>
    </div>
  )
}


function ExecutionHeader({
  detail,
}: {
  detail: {
    status: string
    started_at: string | null
    finished_at: string | null
    error: string | null
  }
}) {
  const dur = computeDuration(detail.started_at, detail.finished_at)
  return (
    <div className="rounded-md border bg-muted/30 p-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-medium">执行状态</span>
        <StatusBadge status={detail.status} />
      </div>
      {dur && (
        <div className="mt-1 text-muted-foreground">总耗时 {dur}</div>
      )}
      {detail.error && (
        <div className="mt-1 rounded bg-red-50 p-1.5 text-[11px] text-red-900 dark:bg-red-950 dark:text-red-200">
          {detail.error}
        </div>
      )}
    </div>
  )
}


function NodeStep({
  index,
  node,
  isTrigger,
}: {
  index: number
  node: NodeDetail
  isTrigger: boolean
}) {
  const hasInputs = node.input && Object.keys(node.input).length > 0
  return (
    <div className="space-y-1 rounded-md border p-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="inline-flex size-5 items-center justify-center rounded-full bg-muted text-[10px] font-medium">
            {index}
          </span>
          <div>
            <div className="text-xs font-medium">{nodeNameCn(node.type)}</div>
            <div className="text-[10px] text-muted-foreground">{node.node_id}</div>
          </div>
        </div>
        <StatusBadge status={node.status} />
      </div>
      {node.error && (
        <div className="rounded bg-red-50 p-1.5 text-[11px] text-red-900 dark:bg-red-950 dark:text-red-200">
          {node.error}
        </div>
      )}
      {/* 输入 = 这次执行节点实际收到的 resolved 值（后端快照），不随画布后续编辑变化。
          触发节点没有 data.inputs 概念，跳过。 */}
      {hasInputs && !isTrigger && (
        <OutputBlock value={node.input} label="输入" />
      )}
      {node.output != null && (
        <OutputBlock value={node.output} label="输出" />
      )}
    </div>
  )
}


// （input 现在直接由后端快照提供，前端不再需要 resolveInputs / resolveSelector）


function StatusBadge({ status }: { status: string }) {
  const cls: Record<string, string> = {
    succeeded: "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200",
    running: "bg-blue-100 text-blue-900 dark:bg-blue-950 dark:text-blue-200",
    failed: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
    skipped: "bg-gray-100 text-gray-700 dark:bg-gray-900 dark:text-gray-300",
    cancelled: "bg-yellow-100 text-yellow-900 dark:bg-yellow-950 dark:text-yellow-200",
    waiting: "bg-orange-100 text-orange-900 dark:bg-orange-950 dark:text-orange-200",
  }
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] ${cls[status] ?? ""}`}>
      {status}
    </span>
  )
}


function computeDuration(start: string | null, end: string | null): string | null {
  if (!start || !end) return null
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (!Number.isFinite(ms) || ms < 0) return null
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}


/**
 * 按执行拓扑给节点排序（Kahn 算法）。入度为 0 的 trigger / 孤立节点先，
 * 然后按 edge 关系递推下游。保证 UI 顺序 = 执行顺序。
 */
function orderByTopology<T extends { node_id: string }>(
  nodeDetails: T[],
  canvasNodes: Array<{ id: string }>,
  canvasEdges: Array<{ source: string; target: string }>,
): T[] {
  const byId = new Map(nodeDetails.map((n) => [n.node_id, n]))
  const relevantIds = canvasNodes
    .map((n) => n.id)
    .filter((id) => byId.has(id))

  const inDeg = new Map<string, number>(relevantIds.map((id) => [id, 0]))
  const adj = new Map<string, string[]>(relevantIds.map((id) => [id, []]))
  for (const e of canvasEdges) {
    if (inDeg.has(e.target) && adj.has(e.source)) {
      inDeg.set(e.target, (inDeg.get(e.target) ?? 0) + 1)
      adj.get(e.source)!.push(e.target)
    }
  }

  const queue: string[] = relevantIds.filter((id) => (inDeg.get(id) ?? 0) === 0)
  const ordered: T[] = []
  const emitted = new Set<string>()
  while (queue.length) {
    const id = queue.shift()!
    if (emitted.has(id)) continue
    emitted.add(id)
    const d = byId.get(id)
    if (d) ordered.push(d)
    for (const t of adj.get(id) ?? []) {
      const cur = (inDeg.get(t) ?? 0) - 1
      inDeg.set(t, cur)
      if (cur <= 0) queue.push(t)
    }
  }

  // 兜底：canvas 里已不存在的节点（已删除）或 cycle 中剩余的，追加到末尾。
  for (const d of nodeDetails) {
    if (!emitted.has(d.node_id)) ordered.push(d)
  }
  return ordered
}
