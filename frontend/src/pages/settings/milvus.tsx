import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import {
  Activity, AlertTriangle, CheckCircle2, ExternalLink, Loader2,
  RefreshCw, Search, Wrench,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { knowledgeApi } from "@/api/knowledge"
import {
  milvusGovApi,
  type MilvusKBHealth,
  type MilvusTaskStatus,
} from "@/api/milvus_governance"

// 与 docker/docker-compose.override.yml 中 attu 的端口映射保持一致
const ATTU_URL = (import.meta.env.VITE_ATTU_URL as string | undefined) ?? "http://localhost:3000"

type RowBusyState = { kind: "scan" | "clean" | "reindex"; taskId?: string } | null

function statusChip(row: MilvusKBHealth) {
  if (!row.collection_exists) {
    return <Badge variant="secondary">未建索引</Badge>
  }
  if (!row.dim_matches && row.kb_dim !== null && row.milvus_dim !== null) {
    return <Badge variant="destructive">维度不匹配</Badge>
  }
  if (row.orphan_estimate > 0) {
    return <Badge variant="warning">疑似孤儿 {row.orphan_estimate}</Badge>
  }
  if (row.pg_unembedded > 0) {
    return <Badge variant="info">待 embed {row.pg_unembedded}</Badge>
  }
  return <Badge variant="success">一致</Badge>
}

function dimDisplay(row: MilvusKBHealth): string {
  const k = row.kb_dim ?? "—"
  const m = row.milvus_dim ?? "—"
  return `${k} ↔ ${m}`
}

export default function MilvusGovernancePage() {
  const [rows, setRows] = useState<MilvusKBHealth[]>([])
  const [loading, setLoading] = useState(true)
  /** kb_id → 当前在跑什么任务 */
  const [busyMap, setBusyMap] = useState<Record<string, RowBusyState>>({})
  /** 巡检发现孤儿后弹清理确认；存 task 返回的统计供文案展示 */
  const [pendingClean, setPendingClean] = useState<{
    kbId: string; kbName: string; orphanCount: number
  } | null>(null)
  const [pendingReindex, setPendingReindex] = useState<{
    kbId: string; kbName: string
  } | null>(null)
  const pollersRef = useRef<Record<string, number>>({})

  const fetchOverview = useCallback(async () => {
    setLoading(true)
    try {
      const res = await milvusGovApi.overview()
      setRows(res.items)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchOverview()
    const ref = pollersRef.current
    return () => {
      Object.values(ref).forEach((id) => window.clearInterval(id))
    }
  }, [fetchOverview])

  const setBusy = (kbId: string, state: RowBusyState) =>
    setBusyMap((prev) => ({ ...prev, [kbId]: state }))

  const stopPoller = (kbId: string) => {
    const id = pollersRef.current[kbId]
    if (id) {
      window.clearInterval(id)
      delete pollersRef.current[kbId]
    }
  }

  const pollTask = (
    kbId: string,
    taskId: string,
    onDone: (s: MilvusTaskStatus) => void,
  ) => {
    stopPoller(kbId)
    pollersRef.current[kbId] = window.setInterval(async () => {
      try {
        const status = await milvusGovApi.taskStatus(taskId)
        if (status.state === "SUCCESS" || status.state === "FAILURE" || status.state === "REVOKED") {
          stopPoller(kbId)
          onDone(status)
        }
      } catch {
        // 网络抖动单次失败不停轮询；连续失败由后端任务自身超时
      }
    }, 2000)
  }

  // 「巡检孤儿」单按钮流程：scan → 显示 N → 弹确认 → clean
  const handleScanOrphans = async (row: MilvusKBHealth) => {
    setBusy(row.kb_id, { kind: "scan" })
    try {
      const { task_id } = await milvusGovApi.scanOrphans(row.kb_id)
      pollTask(row.kb_id, task_id, (status) => {
        if (status.state !== "SUCCESS" || !status.result) {
          toast.error(`扫描失败：${status.error ?? status.state}`)
          setBusy(row.kb_id, null)
          return
        }
        const r = status.result
        if (r.status === "skipped") {
          toast.info(`跳过：${r.reason ?? "未知原因"}`)
          setBusy(row.kb_id, null)
          return
        }
        const count = r.orphan_count ?? 0
        if (count === 0) {
          toast.success(`${row.kb_name}：未发现孤儿向量`)
          setBusy(row.kb_id, null)
          fetchOverview()
        } else {
          setBusy(row.kb_id, null)
          setPendingClean({ kbId: row.kb_id, kbName: row.kb_name, orphanCount: count })
        }
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "扫描启动失败")
      setBusy(row.kb_id, null)
    }
  }

  const handleConfirmClean = async () => {
    if (!pendingClean) return
    const { kbId, kbName } = pendingClean
    setBusy(kbId, { kind: "clean" })
    setPendingClean(null)
    try {
      const { task_id } = await milvusGovApi.cleanOrphans(kbId)
      pollTask(kbId, task_id, (status) => {
        if (status.state === "SUCCESS" && status.result) {
          const r = status.result
          if (r.status === "skipped") {
            toast.info(`跳过：${r.reason ?? "未知原因"}`)
          } else {
            toast.success(`${kbName}：已清理 ${r.deleted ?? 0} 个孤儿向量`)
          }
        } else {
          toast.error(`清理失败：${status.error ?? status.state}`)
        }
        setBusy(kbId, null)
        fetchOverview()
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "清理启动失败")
      setBusy(kbId, null)
    }
  }

  const handleReindex = async () => {
    if (!pendingReindex) return
    const { kbId, kbName } = pendingReindex
    setPendingReindex(null)
    setBusy(kbId, { kind: "reindex" })
    try {
      await knowledgeApi.reindexKB(kbId)
      toast.success(`${kbName}：重建索引已启动，运行时间取决于 chunks 总量，请稍后刷新`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "重建启动失败")
    } finally {
      // reindex 没有简单的轮询入口，先放手；用户手动刷新看效果
      setTimeout(() => {
        setBusy(kbId, null)
        fetchOverview()
      }, 1500)
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Milvus 治理</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            PG ↔ Milvus 双写一致性巡检：孤儿向量清理 / 维度对账 / 索引重建
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchOverview} disabled={loading}>
            <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} />
            <span className="ml-1">刷新</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open(ATTU_URL, "_blank", "noopener")}
          >
            <ExternalLink className="size-4" />
            <span className="ml-1">打开 Attu</span>
          </Button>
        </div>
      </header>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">KB 名称</th>
              <th className="px-3 py-2 text-right">PG</th>
              <th className="px-3 py-2 text-right">Milvus</th>
              <th className="px-3 py-2">维度 (KB↔Milvus)</th>
              <th className="px-3 py-2">状态</th>
              <th className="px-3 py-2 w-56" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  <Loader2 className="mx-auto size-4 animate-spin" />
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  暂无知识库
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const busy = busyMap[row.kb_id]
                return (
                  <tr key={row.kb_id} className="border-b last:border-0">
                    <td className="px-3 py-2">
                      <div className="font-medium">{row.kb_name}</div>
                      <div className="text-xs text-muted-foreground">
                        {row.source_type} · {row.embedding_model_name ?? "未配置模型"}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {row.pg_count.toLocaleString()}
                      {row.pg_unembedded > 0 && (
                        <span className="ml-1 text-xs text-info">
                          (-{row.pg_unembedded})
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {row.collection_exists
                        ? row.milvus_count.toLocaleString()
                        : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-3 py-2 tabular-nums text-xs">
                      {row.dim_matches ? (
                        <span className="inline-flex items-center gap-1 text-success">
                          <CheckCircle2 className="size-3.5" />
                          {dimDisplay(row)}
                        </span>
                      ) : row.kb_dim !== null && row.milvus_dim !== null ? (
                        <span className="inline-flex items-center gap-1 text-destructive">
                          <AlertTriangle className="size-3.5" />
                          {dimDisplay(row)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">{dimDisplay(row)}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">{statusChip(row)}</td>
                    <td className="px-3 py-2">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!!busy}
                          onClick={() => handleScanOrphans(row)}
                        >
                          {busy?.kind === "scan" ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : busy?.kind === "clean" ? (
                            <Activity className="size-3.5 animate-pulse" />
                          ) : (
                            <Search className="size-3.5" />
                          )}
                          <span className="ml-1">
                            {busy?.kind === "clean" ? "清理中" : "巡检孤儿"}
                          </span>
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={!!busy}
                          onClick={() => setPendingReindex({
                            kbId: row.kb_id, kbName: row.kb_name,
                          })}
                        >
                          {busy?.kind === "reindex" ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : (
                            <Wrench className="size-3.5" />
                          )}
                          <span className="ml-1">重建索引</span>
                        </Button>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!pendingClean}
        onOpenChange={(v) => !v && setPendingClean(null)}
        title={`清理 ${pendingClean?.kbName ?? ""} 的孤儿向量`}
        description={`扫描发现 ${pendingClean?.orphanCount ?? 0} 个孤儿向量（milvus 在册但 PG 无对应 chunk），将批量删除。任务执行时会重新扫描，不会误删此刻新增的向量。是否继续？`}
        confirmText="清理"
        destructive
        onConfirm={handleConfirmClean}
      />

      <ConfirmDialog
        open={!!pendingReindex}
        onOpenChange={(v) => !v && setPendingReindex(null)}
        title={`重建 ${pendingReindex?.kbName ?? ""} 的索引`}
        description="重建会 drop 整个 milvus collection 并基于 PG chunks 全量重新 embed。耗时取决于 chunks 总量；执行期间检索功能短暂不可用。仅在维度不匹配 / 切换 embedding 模型 / 大量孤儿后才需要做。"
        confirmText="重建"
        destructive
        onConfirm={handleReindex}
      />
    </div>
  )
}
