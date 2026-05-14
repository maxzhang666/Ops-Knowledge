import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import {
  AlertOctagon, AlertTriangle, CheckCircle2, Copy, RefreshCw, RotateCcw, X, Zap,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "@/components/ui/sheet"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { TimeDisplay } from "@/components/shared/time-display"
import {
  taskFailuresApi,
  type TaskFailureItem,
  type TaskFailureDetail,
  type TaskFailureState,
} from "@/api/task_failures"

const STATE_OPTIONS: { value: TaskFailureState | "ALL"; label: string }[] = [
  { value: "ALL", label: "全部状态" },
  { value: "FAILURE", label: "FAILURE 异常" },
  { value: "UNREGISTERED", label: "UNREGISTERED 未注册" },
  { value: "TIMEOUT", label: "TIMEOUT 超时" },
]

function stateChip(state: TaskFailureState) {
  if (state === "FAILURE") return <Badge variant="destructive">FAILURE</Badge>
  if (state === "UNREGISTERED") return <Badge variant="info">UNREGISTERED</Badge>
  return <Badge variant="warning">TIMEOUT</Badge>
}

function shortTaskName(name: string): string {
  // app.knowledge.milvus.governance_tasks.scan_orphan_vectors → governance_tasks.scan_orphan_vectors
  const parts = name.split(".")
  return parts.slice(-2).join(".")
}

async function copyToClipboard(text: string, label: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(`${label}已复制`)
  } catch {
    toast.error("复制失败")
  }
}

export default function TaskFailuresPage() {
  const [items, setItems] = useState<TaskFailureItem[]>([])
  const [loading, setLoading] = useState(true)
  const [filterState, setFilterState] = useState<TaskFailureState | "ALL">("ALL")
  const [filterResolved, setFilterResolved] = useState<"all" | "unresolved" | "resolved">("unresolved")
  const [detail, setDetail] = useState<TaskFailureDetail | null>(null)
  const [retryTarget, setRetryTarget] = useState<TaskFailureItem | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  // #4 — 待向量化 chunk backlog (vector_id IS NULL 且 5min+)
  const [backlogCount, setBacklogCount] = useState<number | null>(null)
  const [backlogBusy, setBacklogBusy] = useState(false)

  const fetchList = useCallback(async () => {
    setLoading(true)
    try {
      const params: Parameters<typeof taskFailuresApi.list>[0] = { page: 1, page_size: 50 }
      if (filterState !== "ALL") params.state = filterState
      if (filterResolved === "resolved") params.resolved = true
      if (filterResolved === "unresolved") params.resolved = false
      const res = await taskFailuresApi.list(params)
      setItems(res.items)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [filterState, filterResolved])

  useEffect(() => {
    fetchList()
  }, [fetchList])

  const fetchBacklog = useCallback(async () => {
    try {
      const { count } = await taskFailuresApi.vectorBacklog()
      setBacklogCount(count)
    } catch {
      // 静默 — 卡片不显示
    }
  }, [])

  useEffect(() => {
    fetchBacklog()
  }, [fetchBacklog])

  async function handleCompensateBacklog() {
    setBacklogBusy(true)
    try {
      const { task_id } = await taskFailuresApi.compensateVectorBacklog()
      toast.success(`已触发补偿任务（id: ${task_id.slice(0, 8)}…），稍后刷新查看效果`)
      // 等几秒再刷一次让 worker 处理完
      setTimeout(fetchBacklog, 4000)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "触发失败")
    } finally {
      setBacklogBusy(false)
    }
  }

  async function openDetail(id: string) {
    try {
      const d = await taskFailuresApi.get(id)
      setDetail(d)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载详情失败")
    }
  }

  async function handleConfirmRetry() {
    if (!retryTarget) return
    setBusyId(retryTarget.id)
    setRetryTarget(null)
    try {
      const { task_id } = await taskFailuresApi.retry(retryTarget.id)
      toast.success(`已重放：${shortTaskName(retryTarget.task_name)} (new task_id: ${task_id.slice(0, 8)}…)`)
      fetchList()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "重放失败")
    } finally {
      setBusyId(null)
    }
  }

  async function handleResolve(item: TaskFailureItem) {
    setBusyId(item.id)
    try {
      await taskFailuresApi.resolve(item.id)
      toast.success("已标记为处理")
      fetchList()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "操作失败")
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">队列治理</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Celery 队列异常 / 未注册任务 / 超时持久化日志；支持手动重放与标记已处理；90 天后自动清理
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { fetchList(); fetchBacklog() }} disabled={loading}>
          <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} />
          <span className="ml-1">刷新</span>
        </Button>
      </header>

      {/* #4 — 待向量化 chunk backlog；> 0 时显示警示卡 + 立即补偿按钮 */}
      {backlogCount !== null && backlogCount > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-md border border-warning/30 bg-warning/5 px-4 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
            <div className="text-sm">
              <div className="font-medium">
                有 {backlogCount} 个 chunk 落 PG 超 5 分钟仍未向量化
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                可能原因：broker 不可达 dispatch 失败 / worker 异常退出 / 任务丢失。
                Beat 每 5 分钟自动补偿一次；或点右侧立即触发。
              </div>
            </div>
          </div>
          <Button
            size="sm"
            onClick={handleCompensateBacklog}
            disabled={backlogBusy}
          >
            <Zap className="mr-1 size-3.5" />
            {backlogBusy ? "触发中..." : "立即补偿"}
          </Button>
        </div>
      )}

      <div className="flex items-center gap-2">
        <select
          value={filterState}
          onChange={(e) => setFilterState(e.target.value as TaskFailureState | "ALL")}
          className="h-9 rounded-md border bg-background px-3 text-sm"
        >
          {STATE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select
          value={filterResolved}
          onChange={(e) => setFilterResolved(e.target.value as "all" | "unresolved" | "resolved")}
          className="h-9 rounded-md border bg-background px-3 text-sm"
        >
          <option value="unresolved">仅未处理</option>
          <option value="resolved">仅已处理</option>
          <option value="all">全部</option>
        </select>
      </div>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">任务</th>
              <th className="px-3 py-2">状态</th>
              <th className="px-3 py-2">KB</th>
              <th className="px-3 py-2">失败时间</th>
              <th className="px-3 py-2 text-right">重试</th>
              <th className="px-3 py-2 w-72" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  加载中...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  暂无失败任务
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr
                  key={item.id}
                  className="cursor-pointer border-b last:border-0 hover:bg-muted/30"
                  onClick={() => openDetail(item.id)}
                >
                  <td className="px-3 py-2">
                    <div className="font-mono text-xs">{shortTaskName(item.task_name)}</div>
                    {item.exception && (
                      <div className="mt-0.5 truncate text-xs text-muted-foreground" title={item.exception}>
                        {item.exception}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">{stateChip(item.state)}</td>
                  <td className="px-3 py-2">
                    {item.kb_id ? (
                      <Link
                        to={`/knowledge/${item.kb_id}`}
                        className="text-xs text-info underline-offset-2 hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {item.kb_id.slice(0, 8)}…
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    <TimeDisplay value={item.failed_at} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{item.retries}</td>
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-1">
                      {item.resolved_at ? (
                        <Badge variant="success" className="gap-1">
                          <CheckCircle2 className="size-3" />已处理
                        </Badge>
                      ) : (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={busyId === item.id}
                            onClick={() => setRetryTarget(item)}
                          >
                            <RotateCcw className="size-3.5" />
                            <span className="ml-1">重放</span>
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busyId === item.id}
                            onClick={() => handleResolve(item)}
                          >
                            <CheckCircle2 className="size-3.5" />
                            <span className="ml-1">已处理</span>
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Sheet open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <SheetContent className="w-[640px] sm:max-w-[640px]">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <AlertOctagon className="size-4 text-destructive" />
              <span className="font-mono text-sm">{detail && shortTaskName(detail.task_name)}</span>
              {detail && stateChip(detail.state)}
            </SheetTitle>
          </SheetHeader>
          {detail && (
            <div className="mt-4 space-y-4 overflow-y-auto pr-2">
              <Section title="基本信息">
                <KV label="task_name" value={detail.task_name} mono copyable />
                <KV label="task_id" value={detail.task_id ?? "—"} mono copyable />
                <KV label="retries" value={String(detail.retries)} />
                <KV label="failed_at" value={new Date(detail.failed_at).toLocaleString()} />
                {detail.retried_at && (
                  <KV label="retried_at" value={new Date(detail.retried_at).toLocaleString()} />
                )}
                {detail.resolved_at && (
                  <KV label="resolved_at" value={new Date(detail.resolved_at).toLocaleString()} />
                )}
              </Section>

              <Section title="参数 args / kwargs">
                <pre className="overflow-x-auto rounded-md border bg-muted/30 p-2 text-xs">
                  {JSON.stringify(
                    { args: detail.args_json, kwargs: detail.kwargs_json },
                    null, 2,
                  )}
                </pre>
              </Section>

              <Section title="异常">
                <pre className="overflow-x-auto rounded-md border bg-destructive/5 p-2 text-xs text-destructive">
                  {detail.exception ?? "(no exception)"}
                </pre>
              </Section>

              {detail.traceback && (
                <Section title="Traceback">
                  <pre className="max-h-72 overflow-auto rounded-md border bg-muted/30 p-2 text-[11px] font-mono">
                    {detail.traceback}
                  </pre>
                </Section>
              )}

              {!detail.resolved_at && (
                <div className="flex gap-2 border-t pt-3">
                  <Button
                    onClick={() => {
                      setRetryTarget({
                        id: detail.id,
                        task_id: detail.task_id,
                        task_name: detail.task_name,
                        state: detail.state,
                        exception: detail.exception,
                        retries: detail.retries,
                        kb_id: detail.kb_id,
                        actor_id: detail.actor_id,
                        failed_at: detail.failed_at,
                        retried_at: detail.retried_at,
                        resolved_at: detail.resolved_at,
                      })
                      setDetail(null)
                    }}
                  >
                    <RotateCcw className="size-4" />
                    <span className="ml-1">重放</span>
                  </Button>
                  <Button
                    variant="outline"
                    onClick={async () => {
                      await handleResolve({
                        id: detail.id,
                        task_id: detail.task_id,
                        task_name: detail.task_name,
                        state: detail.state,
                        exception: detail.exception,
                        retries: detail.retries,
                        kb_id: detail.kb_id,
                        actor_id: detail.actor_id,
                        failed_at: detail.failed_at,
                        retried_at: detail.retried_at,
                        resolved_at: detail.resolved_at,
                      })
                      setDetail(null)
                    }}
                  >
                    <CheckCircle2 className="size-4" />
                    <span className="ml-1">标记已处理</span>
                  </Button>
                  <Button variant="ghost" onClick={() => setDetail(null)}>
                    <X className="size-4" />
                    <span className="ml-1">关闭</span>
                  </Button>
                </div>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={!!retryTarget}
        onOpenChange={(v) => !v && setRetryTarget(null)}
        title={`重放 ${retryTarget ? shortTaskName(retryTarget.task_name) : ""}`}
        description={
          retryTarget
            ? `将以原 args/kwargs 重新派发该 task 到 worker 队列。新 task_id 会生成，原行将自动标记已处理。\n\n完整 task name: ${retryTarget.task_name}`
            : ""
        }
        confirmText="重放"
        destructive
        onConfirm={handleConfirmRetry}
      />
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

function KV({
  label, value, mono, copyable,
}: {
  label: string; value: string; mono?: boolean; copyable?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className={`min-w-0 flex-1 truncate text-right ${mono ? "font-mono text-xs" : ""}`}>
        {value}
      </span>
      {copyable && value !== "—" && (
        <Button
          variant="ghost"
          size="icon"
          className="size-6 shrink-0"
          onClick={() => copyToClipboard(value, label)}
        >
          <Copy className="size-3" />
        </Button>
      )}
    </div>
  )
}
