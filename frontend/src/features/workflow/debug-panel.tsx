import { useCallback, useEffect, useRef, useState } from "react"
import { ChevronDown, ChevronUp, Copy, Play, Square } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { workflowApi } from "@/api/workflow"
import { connectExecutionEvents, type WsEvent } from "./ws"
import { useEditorStore } from "./store"
import { NodeOutputRow, OutputBlock, copyToClipboard } from "./debug/output-view"

const STATUS_COLOR: Record<string, string> = {
  waiting: "bg-muted text-muted-foreground",
  running: "bg-blue-100 text-blue-900 dark:bg-blue-950 dark:text-blue-200",
  succeeded: "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200",
  failed: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  skipped: "bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-400",
  cancelled: "bg-yellow-100 text-yellow-900 dark:bg-yellow-950 dark:text-yellow-200",
}


export function DebugPanel() {
  const workflow = useEditorStore((s) => s.workflow)
  const nodes = useEditorStore((s) => s.nodes)
  const execution = useEditorStore((s) => s.execution)
  const startExecution = useEditorStore((s) => s.startExecution)
  const recordNodeStatus = useEditorStore((s) => s.recordNodeStatus)
  const recordNodeOutput = useEditorStore((s) => s.recordNodeOutput)
  const appendStreamChunk = useEditorStore((s) => s.appendStreamChunk)
  const finishExecution = useEditorStore((s) => s.finishExecution)
  const clearExecution = useEditorStore((s) => s.clearExecution)

  const [expanded, setExpanded] = useState(true)
  const [inputsText, setInputsText] = useState("{}")
  // Final output picked by heuristics from the persisted snapshot (see
  // `pickTerminalOutput`). Shown when the run produced no stream_chunks —
  // e.g. stream-less nodes, or WS connected too late to catch them.
  const [finalOutput, setFinalOutput] = useState<unknown>(undefined)
  const unsubRef = useRef<(() => void) | null>(null)
  const streamRef = useRef<HTMLPreElement | null>(null)

  const handleEvent = useCallback(
    (ev: WsEvent) => {
      if (ev.type === "node_start" && ev.node_id) {
        recordNodeStatus(ev.node_id, "running")
      } else if (ev.type === "node_output" && ev.node_id) {
        // Store per-node output as it arrives (live).
        if (ev.data.outputs !== undefined) recordNodeOutput(ev.node_id, ev.data.outputs)
      } else if (ev.type === "node_error" && ev.node_id) {
        recordNodeStatus(ev.node_id, "failed", String(ev.data.error ?? ""))
      } else if (ev.type === "node_end" && ev.node_id) {
        recordNodeStatus(ev.node_id, String(ev.data.status ?? "succeeded"))
      } else if (ev.type === "stream_chunk") {
        const delta = ev.data.delta as string | undefined
        if (delta) appendStreamChunk(delta)
      } else if (ev.type === "workflow_end") {
        finishExecution(String(ev.data.status ?? "succeeded"))
        // After the run ends, fetch the persisted snapshot so node outputs /
        // errors are visible even if we missed mid-stream events (late WS,
        // bus history truncated, scheduler failed before emitting).
        const wfId = workflow?.id
        const execId = execution?.id
        if (wfId && execId) {
          workflowApi.getExecution(wfId, execId)
            .then((detail) => {
              for (const n of detail.nodes) {
                recordNodeStatus(
                  n.node_id, n.status,
                  n.error ? String(n.error) : undefined,
                )
                if (n.output !== undefined && n.output !== null) {
                  recordNodeOutput(n.node_id, n.output)
                }
              }
              setFinalOutput(pickTerminalOutput(detail.output, detail.nodes))
            })
            .catch(() => { /* best-effort */ })
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      recordNodeStatus, recordNodeOutput, appendStreamChunk,
      finishExecution, workflow?.id, execution?.id,
    ],
  )

  useEffect(() => {
    return () => { unsubRef.current?.() }
  }, [])

  useEffect(() => {
    if (!streamRef.current) return
    streamRef.current.scrollTop = streamRef.current.scrollHeight
  }, [execution?.stream.length])

  async function handleRun() {
    if (!workflow) return
    let inputs: Record<string, unknown> = {}
    try {
      inputs = JSON.parse(inputsText || "{}")
    } catch {
      toast.error("inputs 不是合法 JSON")
      return
    }
    try {
      const res = await workflowApi.run(workflow.id, inputs, { from_draft: true })
      setFinalOutput(undefined)
      startExecution(res.execution_id)
      unsubRef.current?.()
      unsubRef.current = connectExecutionEvents(
        workflow.id, res.execution_id, handleEvent,
      )
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "启动失败")
    }
  }

  async function handleCancel() {
    if (!workflow || !execution) return
    try {
      await workflowApi.cancelExecution(workflow.id, execution.id)
      toast.message("已发送取消信号")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "取消失败")
    }
  }

  const isRunning = execution?.status === "running"
  const streamJoined = (execution?.stream ?? []).join("")
  const hasStream = streamJoined.length > 0

  return (
    <div className="flex flex-col border-t">
      <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-1.5 text-xs">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 font-medium"
        >
          {expanded ? <ChevronDown className="size-3.5" /> : <ChevronUp className="size-3.5" />}
          调试
          {execution && (
            <span className={`ml-2 rounded px-1 ${STATUS_COLOR[execution.status] ?? ""}`}>
              {execution.status}
            </span>
          )}
        </button>
        <div className="flex items-center gap-2">
          <input
            className="rounded border bg-background px-2 py-0.5 font-mono text-[11px]"
            style={{ width: 240 }}
            placeholder='inputs JSON, e.g. {"query":"hi"}'
            value={inputsText}
            onChange={(e) => setInputsText(e.target.value)}
          />
          {isRunning ? (
            <Button size="sm" variant="destructive" onClick={handleCancel}>
              <Square className="mr-1 size-3" /> 取消
            </Button>
          ) : (
            <Button size="sm" onClick={handleRun}>
              <Play className="mr-1 size-3" /> 试运行
            </Button>
          )}
          {execution && !isRunning && (
            <Button size="sm" variant="ghost" onClick={clearExecution}>
              清除
            </Button>
          )}
        </div>
      </div>

      {expanded && (
        <div
          className="grid grid-cols-[1fr_1fr] gap-3 p-3 text-xs"
          style={{ minHeight: 180, maxHeight: 420, overflow: "hidden" }}
        >
          <div className="overflow-y-auto pr-1">
            <div className="mb-1 font-medium">节点</div>
            {nodes.length === 0 ? (
              <p className="text-muted-foreground">画布为空</p>
            ) : (
              <div className="space-y-1">
                {nodes.map((n) => {
                  const status = execution?.nodes[n.id] ?? "waiting"
                  const err = execution?.nodeErrors[n.id]
                  const out = execution?.nodeOutputs[n.id]
                  const nodeType = ((n.data as { nodeType?: string })?.nodeType) ?? "?"
                  return (
                    <NodeOutputRow
                      key={n.id}
                      nodeId={n.id}
                      nodeType={nodeType}
                      status={status}
                      error={err}
                      output={out}
                      statusClass={STATUS_COLOR[status] ?? ""}
                    />
                  )
                })}
              </div>
            )}
          </div>
          <div className="overflow-y-auto pl-1">
            <div className="mb-1 flex items-center justify-between font-medium">
              <span>输出</span>
              <div className="flex items-center gap-2">
                {hasStream && (
                  <span className="text-[10px] text-muted-foreground">流式</span>
                )}
                {!hasStream && finalOutput !== undefined && (
                  <span className="text-[10px] text-muted-foreground">终态快照</span>
                )}
                {hasStream && (
                  <button
                    type="button"
                    onClick={() => copyToClipboard(streamJoined)}
                    className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
                  >
                    <Copy className="size-3" /> 复制
                  </button>
                )}
              </div>
            </div>
            {hasStream ? (
              <pre
                ref={streamRef}
                className="max-h-full whitespace-pre-wrap rounded border bg-background p-2 font-mono text-[11px]"
                style={{ minHeight: 120, maxHeight: 340, overflow: "auto" }}
              >
                {streamJoined}
              </pre>
            ) : finalOutput !== undefined ? (
              <OutputBlock value={finalOutput} />
            ) : (
              <div className="rounded border bg-background p-2 text-[11px] text-muted-foreground">
                （等待执行完成...）
              </div>
            )}
          </div>
        </div>
      )}

      {workflow?.status !== "published" && (
        <div className="bg-blue-50 px-3 py-1 text-[11px] text-blue-900 dark:bg-blue-950 dark:text-blue-200">
          当前为草稿 — 试运行基于未发布的草稿；发布后外部调用才会切换到发布版本。
        </div>
      )}
    </div>
  )
}


/**
 * Pick the "most interesting" terminal output to surface at the top level
 * of the output panel. Returns the raw value (object / string / etc.) — the
 * OutputBlock component decides how to render.
 *
 * Order:
 *   1. Answer node's full `output` object  (→ friendly answer + references render)
 *   2. LLM node's `output` object          (→ JsonView shows content + usage)
 *   3. Workflow-level `output` (dict of all nodes)
 */
function pickTerminalOutput(
  output: Record<string, unknown> | null,
  nodes: Array<{ node_id: string; type: string; output: Record<string, unknown> | null }>,
): unknown {
  for (const n of nodes) {
    if (n.type === "answer" && n.output) return n.output
  }
  for (const n of nodes) {
    if (n.type === "llm" && n.output) return n.output
  }
  return output ?? undefined
}
