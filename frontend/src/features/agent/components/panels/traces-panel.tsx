/**
 * Orchestrator 路由审计（Plan 31 N2.5）—— 最近决策 + 每条规则命中指标。
 *
 * 上半部分：规则命中概览（hit_count / avg_latency / last_hit）。
 * 下半部分：最近 50 条 traces，点击展开完整 payload（tried_rules、
 * metadata_snapshot、classifier 详情 —— 运营用来排查"为什么这条
 * 规则没命中"）。
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react"
import { toast } from "sonner"

import type { Agent } from "@/api/agent"
import {
  orchestratorApi,
  type OrchestratorTrace,
  type RuleMetrics,
  type AgentRule,
} from "@/api/orchestrator"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/shared/loading-spinner"


const STATUS_BADGE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  ok: "default",
  error: "destructive",
  fallback_next: "secondary",
  fallback_default: "outline",
}


export function TracesPanel({ agent }: { agent: Agent }) {
  const [traces, setTraces] = useState<OrchestratorTrace[]>([])
  const [metrics, setMetrics] = useState<RuleMetrics[]>([])
  const [rules, setRules] = useState<AgentRule[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [t, m, r] = await Promise.all([
        orchestratorApi.listTraces(agent.id, 50),
        orchestratorApi.metrics(agent.id),
        orchestratorApi.listRules(agent.id),
      ])
      setTraces(t)
      setMetrics(m)
      setRules(r)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载审计失败")
    } finally {
      setLoading(false)
    }
  }, [agent.id])

  useEffect(() => { load() }, [load])

  const rulesById = useMemo(() => {
    const m = new Map<string, AgentRule>()
    for (const r of rules) m.set(r.id, r)
    return m
  }, [rules])

  const rankedMetrics = useMemo(
    () => [...metrics].sort((a, b) => b.hit_count - a.hit_count),
    [metrics],
  )

  function toggle(id: string) {
    setExpanded((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">路由审计</h2>
        <Button variant="ghost" size="sm" onClick={load}>
          <RefreshCw className="mr-1 size-3" /> 刷新
        </Button>
      </div>

      {/* Rule metrics table */}
      <section>
        <h3 className="mb-2 text-xs font-medium text-muted-foreground">规则命中概览</h3>
        {rankedMetrics.length === 0 ? (
          <p className="rounded border border-dashed p-4 text-center text-xs text-muted-foreground">
            尚未有路由记录。发几条消息后再回来看。
          </p>
        ) : (
          <div className="overflow-x-auto rounded border">
            <table className="w-full text-xs">
              <thead className="border-b bg-muted/40 text-left text-muted-foreground">
                <tr>
                  <th className="w-24 px-2 py-1.5">规则</th>
                  <th className="px-2 py-1.5">摘要</th>
                  <th className="w-20 px-2 py-1.5 text-right">命中</th>
                  <th className="w-28 px-2 py-1.5">最近命中</th>
                  <th className="w-20 px-2 py-1.5 text-right">均耗</th>
                </tr>
              </thead>
              <tbody>
                {rankedMetrics.map((m) => {
                  const rule = rulesById.get(m.rule_id)
                  return (
                    <tr key={m.rule_id} className="border-b last:border-b-0">
                      <td className="px-2 py-1.5 font-mono text-[10px] text-muted-foreground">
                        {m.rule_id.slice(0, 8)}…
                      </td>
                      <td className="px-2 py-1.5">
                        {rule ? (
                          <>
                            <Badge variant="secondary" className="mr-1 text-[10px]">{rule.match_type}</Badge>
                            <span className="text-muted-foreground">→ {rule.handler_type}</span>
                          </>
                        ) : <span className="text-muted-foreground">(已删除)</span>}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{m.hit_count}</td>
                      <td className="px-2 py-1.5 text-muted-foreground">
                        {m.last_hit_at ? new Date(m.last_hit_at).toLocaleString("zh-CN") : "-"}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
                        {m.avg_latency_ms != null ? `${m.avg_latency_ms}ms` : "-"}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Recent traces */}
      <section>
        <h3 className="mb-2 text-xs font-medium text-muted-foreground">最近 50 条决策</h3>
        {traces.length === 0 ? (
          <p className="rounded border border-dashed p-4 text-center text-xs text-muted-foreground">
            暂无决策记录
          </p>
        ) : (
          <div className="flex flex-col gap-1">
            {traces.map((t) => {
              const isOpen = expanded.has(t.id)
              const status = t.handler_status ?? "unknown"
              return (
                <div key={t.id} className="rounded border">
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 p-2 text-left text-xs hover:bg-muted/30"
                    onClick={() => toggle(t.id)}
                  >
                    {isOpen ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
                    <span className="text-muted-foreground tabular-nums">
                      {new Date(t.created_at).toLocaleTimeString("zh-CN")}
                    </span>
                    <Badge variant={STATUS_BADGE[status] ?? "secondary"} className="text-[10px]">
                      {status}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      {t.match_type_used ?? "?"}
                    </Badge>
                    <span className="flex-1 truncate">{t.user_message}</span>
                    {t.handler_latency_ms != null && (
                      <span className="text-muted-foreground tabular-nums">{t.handler_latency_ms}ms</span>
                    )}
                  </button>
                  {isOpen && (
                    <div className="border-t bg-muted/20 p-2 text-[11px]">
                      <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1">
                        <dt className="text-muted-foreground">matched_rule</dt>
                        <dd className="font-mono">{t.matched_rule_id ?? "(default)"}</dd>
                        <dt className="text-muted-foreground">handler</dt>
                        <dd>{t.handler_type} / <span className="font-mono">{t.handler_id ?? "-"}</span></dd>
                        {t.llm_classifier_category && (
                          <>
                            <dt className="text-muted-foreground">classifier</dt>
                            <dd>
                              {t.llm_classifier_category}{" "}
                              <span className="text-muted-foreground">
                                (conf {t.llm_classifier_confidence?.toFixed(2) ?? "?"}
                                {t.llm_classifier_cached ? ", cached" : ""})
                              </span>
                            </dd>
                          </>
                        )}
                        {t.tried_rules && t.tried_rules.length > 0 && (
                          <>
                            <dt className="text-muted-foreground">tried_rules</dt>
                            <dd className="font-mono text-[10px]">
                              {t.tried_rules.map((id) => id.slice(0, 8)).join(" → ")}
                            </dd>
                          </>
                        )}
                        <dt className="text-muted-foreground">metadata</dt>
                        <dd>
                          <pre className="whitespace-pre-wrap break-all text-[10px]">
                            {JSON.stringify(t.metadata_snapshot ?? {}, null, 2)}
                          </pre>
                        </dd>
                        {t.error && (
                          <>
                            <dt className="text-destructive">error</dt>
                            <dd className="whitespace-pre-wrap text-destructive">{t.error}</dd>
                          </>
                        )}
                      </dl>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
