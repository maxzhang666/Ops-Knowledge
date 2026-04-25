import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertTriangle, ArrowRight, BarChart3, Clock, Database,
  HelpCircle, Leaf, Layers, Play, Save, ShieldCheck, Sparkles, ThermometerSnowflake,
  MessageSquare,
} from "lucide-react"
import { toast } from "sonner"
import { workflowApi } from "@/api/workflow"

import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { EmptyState } from "@/components/shared/empty-state"
import {
  knowledgeApi,
  type GovernanceAlert,
  type GovernanceFacet,
  type GovernanceFacetKey,
  type GovernanceHealth,
  type GovernanceTrendPoint,
  type KBGovernanceConfig,
  type KnowledgeBase,
} from "@/api/knowledge"

/**
 * 治理 Tab —— Plan 32 M2.5
 *
 * 渲染：健康分总览 + 4 个维度卡 + 告警卡 + 7 日趋势 + 治理参数表单。
 *
 * 说明：
 *   - 健康分采用纯 CSS 环形刻度（SVG stroke-dasharray），不引入图表库。
 *   - 告警的 preview 结构按 kind 分支渲染（stale_docs/low_quality_chunks/
 *     knowledge_gap/cold_chunks），保持类型安全的同时避免弹一个泛 JSON。
 */

interface GovernanceTabProps {
  kb: KnowledgeBase
}

const FACET_META: Record<GovernanceFacetKey, { label: string; icon: typeof Sparkles; hint: string }> = {
  chunk_quality: { label: "切片质量", icon: Sparkles, hint: "综合评分（静态 × 动态）平均值" },
  coverage: { label: "覆盖度", icon: BarChart3, hint: "近 30 天被命中过的切片占比" },
  freshness: { label: "内容新鲜度", icon: Leaf, hint: "非过期文档占比" },
  availability: { label: "可用性", icon: ShieldCheck, hint: "近 7 天有结果检索占比" },
  answer_quality: { label: "答案质量", icon: MessageSquare, hint: "LLM-as-judge 近 7 天答案层指标均值" },
}

export function GovernanceTab({ kb }: GovernanceTabProps) {
  const [data, setData] = useState<GovernanceHealth | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await knowledgeApi.governance(kb.id)
      setData(resp)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [kb.id])

  useEffect(() => { load() }, [load])

  if (loading) return <LoadingSpinner className="py-16" />
  if (!data) {
    return (
      <EmptyState
        title="暂无治理数据"
        description="请稍后重试，或先上传文档并触发一次检索以生成事件数据"
      />
    )
  }

  const isEmptyKb =
    (data.facets.chunk_quality?.detail as { empty?: boolean } | undefined)?.empty === true
    && (data.facets.freshness?.detail as { empty?: boolean } | undefined)?.empty === true

  if (isEmptyKb) {
    return (
      <div className="mt-4 flex flex-col gap-4">
        <EmptyState
          title="知识库尚无内容"
          description="上传至少一份文档并等待处理完成，治理仪表盘才会开始计算真实健康分。"
        />
        <ConfigForm kb={kb} onSaved={load} />
      </div>
    )
  }

  return (
    <div className="mt-4 flex flex-col gap-4">
      {/* Top: Health score + facets */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(260px,340px)_1fr]">
        <HealthRing score={data.health_score} generatedAt={data.generated_at} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {(Object.keys(FACET_META) as GovernanceFacetKey[]).map((k) => (
            <FacetCard key={k} facetKey={k} facet={data.facets[k]} />
          ))}
        </div>
      </div>

      {/* Alerts */}
      <AlertSection alerts={data.alerts} kbId={kb.id} />

      {/* Trend */}
      <TrendCard trend={data.trend} />

      {/* Topic distribution */}
      <TopicsCard kbId={kb.id} />

      {/* Plan 35 — Retrieval Strategy Recommendations */}
      <RetrievalRecoCard kbId={kb.id} />

      {/* Config */}
      <ConfigForm kb={kb} onSaved={load} />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// Topic distribution (Plan 26 T4)

function TopicsCard({ kbId }: { kbId: string }) {
  const [topics, setTopics] = useState<Array<{
    cluster_id: number
    label: string
    size: number
    keywords: string[]
  }> | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    knowledgeApi.listTopics(kbId)
      .then((r) => { if (!cancelled) setTopics(r.topics) })
      .catch(() => { if (!cancelled) setTopics([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [kbId])

  if (loading) {
    return (
      <Card size="sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Layers className="size-4 text-primary" /> 话题分布
          </CardTitle>
        </CardHeader>
        <CardContent className="py-4 text-xs text-muted-foreground">加载中…</CardContent>
      </Card>
    )
  }
  if (!topics || topics.length === 0) {
    return (
      <Card size="sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Layers className="size-4 text-primary" /> 话题分布
          </CardTitle>
        </CardHeader>
        <CardContent className="py-4 text-xs text-muted-foreground">
          暂无话题数据 —— 每日后台任务会聚类 chunk embedding 生成代表话题。
        </CardContent>
      </Card>
    )
  }
  const maxSize = Math.max(...topics.map((t) => t.size), 1)
  return (
    <Card size="sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Layers className="size-4 text-primary" /> 话题分布（{topics.length}）
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {topics.map((t) => {
          const pct = (t.size / maxSize) * 100
          return (
            <div key={t.cluster_id} className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="min-w-0 flex-1 truncate font-medium" title={t.label}>
                  {t.label}
                </span>
                <span className="ml-2 shrink-0 text-muted-foreground">{t.size}</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
              </div>
              {t.keywords.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {t.keywords.slice(0, 4).map((k) => (
                    <Badge key={k} variant="outline" className="text-[10px]">{k}</Badge>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────
// Health ring

function HealthRing({ score, generatedAt }: { score: number; generatedAt: string }) {
  const tone = scoreTone(score)
  const radius = 60
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100)

  return (
    <Card size="sm" className="flex flex-col items-center justify-center p-4">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-normal text-muted-foreground">总健康分</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-2">
        <div className="relative size-[152px]">
          <svg viewBox="0 0 152 152" className="-rotate-90">
            <circle cx="76" cy="76" r={radius} className="fill-none stroke-muted" strokeWidth="10" />
            <circle
              cx="76" cy="76" r={radius}
              className={`fill-none ${tone.stroke} transition-all duration-500`}
              strokeWidth="10"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-3xl font-semibold ${tone.text}`}>{score.toFixed(0)}</span>
            <span className="text-[11px] text-muted-foreground">{tone.label}</span>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          生成于 {new Date(generatedAt).toLocaleString()}
        </p>
      </CardContent>
    </Card>
  )
}

function scoreTone(score: number): { stroke: string; text: string; label: string } {
  if (score >= 80) return { stroke: "stroke-success", text: "text-success", label: "良好" }
  if (score >= 60) return { stroke: "stroke-info", text: "text-info", label: "合格" }
  if (score >= 40) return { stroke: "stroke-warning", text: "text-warning", label: "需关注" }
  return { stroke: "stroke-destructive", text: "text-destructive", label: "紧急" }
}

// ─────────────────────────────────────────────────────────────────
// Facet card

function FacetCard({ facetKey, facet }: { facetKey: GovernanceFacetKey; facet: GovernanceFacet | undefined }) {
  const meta = FACET_META[facetKey]
  const Icon = meta.icon
  if (!facet) return null
  const tone = scoreTone(facet.score)

  return (
    <Card size="sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2">
            <Icon className="size-4 text-primary" />
            {meta.label}
          </span>
          <Badge variant="outline" className="font-mono text-[10px]">
            权重 {(facet.weight * 100).toFixed(0)}%
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-baseline gap-2">
          <span className={`text-2xl font-semibold ${tone.text}`}>{facet.score.toFixed(1)}</span>
          <span className="text-xs text-muted-foreground">/ 100</span>
        </div>
        <p className="text-[11px] text-muted-foreground">{meta.hint}</p>
        <FacetDetail facetKey={facetKey} detail={facet.detail} />
      </CardContent>
    </Card>
  )
}

function FacetDetail({ facetKey, detail }: { facetKey: GovernanceFacetKey; detail: Record<string, unknown> }) {
  const pairs: Array<[string, string]> = []
  if (facetKey === "chunk_quality") {
    const avg = detail.avg as number | null
    pairs.push(["平均综合分", avg == null ? "—" : (avg * 100).toFixed(1) + "%"])
    pairs.push(["总切片", String(detail.total_chunks ?? 0)])
  } else if (facetKey === "coverage") {
    pairs.push(["30 天命中", String(detail.hit_chunks_30d ?? 0)])
    pairs.push(["冷切片", String(detail.cold_chunks ?? 0)])
  } else if (facetKey === "freshness") {
    pairs.push(["文档数", String(detail.total_docs ?? 0)])
    pairs.push(["过期", String(detail.stale_docs ?? 0)])
  } else if (facetKey === "availability") {
    pairs.push(["7 天检索", String(detail.total ?? 0)])
    const sr = detail.success_rate as number | null
    pairs.push(["有结果率", sr == null ? "—" : (sr * 100).toFixed(1) + "%"])
  } else if (facetKey === "answer_quality") {
    pairs.push(["样本数", String(detail.samples ?? 0)])
    const avg = detail.avg as number | null
    pairs.push(["均分", avg == null ? "—" : (avg * 100).toFixed(1) + "%"])
  }
  return (
    <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
      {pairs.map(([k, v]) => (
        <div key={k} className="flex items-center justify-between gap-2">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="font-medium">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

// ─────────────────────────────────────────────────────────────────
// Alerts

function AlertSection({ alerts, kbId }: { alerts: GovernanceAlert[]; kbId: string }) {
  if (alerts.length === 0) {
    return (
      <Card size="sm">
        <CardContent className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <ShieldCheck className="size-4 text-success" />
          暂无告警 —— 知识库运行良好。
        </CardContent>
      </Card>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold">告警 ({alerts.length})</h3>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {alerts.map((a, i) => <AlertCard key={`${a.kind}-${i}`} alert={a} kbId={kbId} />)}
      </div>
    </div>
  )
}

const SEVERITY_TONE: Record<GovernanceAlert["severity"], { bar: string; text: string; bg: string; label: string }> = {
  critical: { bar: "bg-destructive", text: "text-destructive", bg: "bg-destructive/5", label: "严重" },
  warning: { bar: "bg-warning", text: "text-warning", bg: "bg-warning/5", label: "警告" },
  info: { bar: "bg-info", text: "text-info", bg: "bg-info/5", label: "提示" },
}

const ALERT_KIND_ICON: Record<GovernanceAlert["kind"], typeof AlertTriangle> = {
  stale_docs: Clock,
  low_quality_chunks: AlertTriangle,
  cold_chunks: ThermometerSnowflake,
  knowledge_gap: HelpCircle,
  redundancy: Database,
}

function AlertCard({ alert, kbId }: { alert: GovernanceAlert; kbId: string }) {
  const tone = SEVERITY_TONE[alert.severity]
  const Icon = ALERT_KIND_ICON[alert.kind] ?? AlertTriangle
  return (
    <Card size="sm" className={tone.bg}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-start gap-2 text-sm">
          <span className={`mt-[3px] h-4 w-1 shrink-0 rounded ${tone.bar}`} />
          <Icon className={`size-4 shrink-0 ${tone.text}`} />
          <span className="min-w-0 flex-1">{alert.title}</span>
          <Badge variant="outline" className={`shrink-0 text-[10px] ${tone.text}`}>
            {tone.label}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <AlertPreview alert={alert} />
        <div className="flex flex-wrap items-center gap-2">
          {alert.action_href && (
            <a
              href={alert.action_href}
              className={buttonVariants({ variant: "ghost", size: "sm" }) + " text-xs"}
            >
              查看详情 <ArrowRight className="ml-1 size-3" />
            </a>
          )}
          <GovernanceRunButton alert={alert} kbId={kbId} />
        </div>
      </CardContent>
    </Card>
  )
}

/** Plan 27 M4 — 一键启动处置 Workflow。列出已发布的 governance_event 触发器，
 * 点击后以 alert data 作为 trigger_input 启动执行。 */
function GovernanceRunButton({ alert, kbId }: { alert: GovernanceAlert; kbId: string }) {
  const [open, setOpen] = useState(false)
  const [handlers, setHandlers] = useState<Array<{ id: string; name: string }> | null>(null)
  const [launching, setLaunching] = useState<string | null>(null)

  const togglePanel = async () => {
    if (open) { setOpen(false); return }
    setOpen(true)
    if (handlers === null) {
      try {
        const rows = await workflowApi.listGovernanceHandlers()
        setHandlers(rows.map((r) => ({ id: r.id, name: r.name })))
      } catch {
        setHandlers([])
      }
    }
  }

  const runOne = async (wfId: string) => {
    setLaunching(wfId)
    try {
      const preview = (alert.preview[0] || {}) as Record<string, unknown>
      const inputs: Record<string, unknown> = {
        kb_id: kbId,
        kind: alert.kind,
        severity: alert.severity,
        count: alert.count,
      }
      if (alert.kind === "stale_docs" && preview.id) inputs.document_id = preview.id
      if (alert.kind === "redundancy") {
        inputs.chunk_a_id = preview.a_id
        inputs.chunk_b_id = preview.b_id
      }
      const res = await workflowApi.run(wfId, inputs)
      toast.success(`已启动处置 (execution ${res.execution_id.slice(0, 8)})`)
      setOpen(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "启动失败")
    } finally {
      setLaunching(null)
    }
  }

  return (
    <div className="relative">
      <Button variant="outline" size="sm" onClick={togglePanel}>
        <Play className="mr-1 size-3" /> 启动处置
      </Button>
      {open && (
        <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-md border bg-popover p-1 shadow-md">
          {handlers === null && (
            <div className="p-2 text-xs text-muted-foreground">加载中…</div>
          )}
          {handlers && handlers.length === 0 && (
            <div className="p-2 text-xs text-muted-foreground">
              尚未配置 governance_event 触发器。请在 Workflow 列表从内置模板创建并发布。
            </div>
          )}
          {handlers && handlers.map((h) => (
            <button
              key={h.id}
              className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs hover:bg-muted"
              disabled={launching !== null}
              onClick={() => runOne(h.id)}
            >
              <span className="truncate">{h.name}</span>
              {launching === h.id && <span className="text-[10px] text-muted-foreground">启动中…</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function AlertPreview({ alert }: { alert: GovernanceAlert }) {
  if (alert.preview.length === 0) return null
  if (alert.kind === "stale_docs") {
    return (
      <ul className="flex flex-col gap-1 text-[11px]">
        {alert.preview.slice(0, 5).map((p) => (
          <li key={String(p.id)} className="flex items-center justify-between gap-2">
            <span className="truncate">{String(p.title ?? "—")}</span>
            <span className="shrink-0 text-muted-foreground">
              {p.updated_at ? new Date(String(p.updated_at)).toLocaleDateString() : "—"}
            </span>
          </li>
        ))}
      </ul>
    )
  }
  if (alert.kind === "low_quality_chunks") {
    return (
      <ul className="flex flex-col gap-1 text-[11px]">
        {alert.preview.slice(0, 5).map((p) => (
          <li key={String(p.id)} className="flex items-center gap-2">
            <Badge variant="outline" className="font-mono text-[10px]">
              {typeof p.score === "number" ? p.score.toFixed(2) : "—"}
            </Badge>
            <span className="line-clamp-1 flex-1 text-muted-foreground">{String(p.preview ?? "")}</span>
          </li>
        ))}
      </ul>
    )
  }
  if (alert.kind === "knowledge_gap") {
    return (
      <ul className="flex flex-col gap-1 text-[11px]">
        {alert.preview.slice(0, 5).map((p, i) => (
          <li key={i} className="flex items-center justify-between gap-2">
            <span className="truncate">{String(p.query ?? "")}</span>
            <Badge variant="secondary" className="shrink-0 text-[10px]">
              × {Number(p.count ?? 0)}
            </Badge>
          </li>
        ))}
      </ul>
    )
  }
  if (alert.kind === "redundancy") {
    return (
      <ul className="flex flex-col gap-2 text-[11px]">
        {alert.preview.slice(0, 5).map((p, i) => (
          <li key={i} className="rounded-md border p-2">
            <div className="mb-1 flex items-center justify-between">
              <Badge variant="outline" className="font-mono text-[10px]">
                sim {Number(p.similarity ?? 0).toFixed(2)}
              </Badge>
            </div>
            <div className="flex flex-col gap-1">
              <span className="line-clamp-1 text-muted-foreground">A · {String(p.a_preview ?? "")}</span>
              <span className="line-clamp-1 text-muted-foreground">B · {String(p.b_preview ?? "")}</span>
            </div>
          </li>
        ))}
      </ul>
    )
  }
  return null
}

// ─────────────────────────────────────────────────────────────────
// Trend (7d sparkline)

function TrendCard({ trend }: { trend: GovernanceHealth["trend"] }) {
  const maxV = useMemo(() => {
    const all = [...trend.hits, ...trend.adopted].map((p) => p.v)
    return Math.max(1, ...all)
  }, [trend])

  return (
    <Card size="sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <BarChart3 className="size-4 text-primary" /> 7 日趋势
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Sparkline label="命中" points={trend.hits} max={maxV} cls="stroke-primary" />
        <Sparkline label="采用" points={trend.adopted} max={maxV} cls="stroke-success" />
      </CardContent>
    </Card>
  )
}

function Sparkline({ label, points, max, cls }: { label: string; points: GovernanceTrendPoint[]; max: number; cls: string }) {
  const w = 560
  const h = 48
  const padX = 4
  const padY = 4
  const innerW = w - padX * 2
  const innerH = h - padY * 2
  const total = Math.max(1, points.length - 1)
  const path = points
    .map((p, i) => {
      const x = padX + (i / total) * innerW
      const y = padY + innerH - (p.v / max) * innerH
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
  const sum = points.reduce((acc, p) => acc + p.v, 0)

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="flex items-center gap-1.5">
          <span className={`size-2 rounded-sm ${cls.replace("stroke-", "bg-")}`} />
          <span className="text-muted-foreground">{label}</span>
        </span>
        <span className="text-muted-foreground">共 {sum}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-12 w-full">
        <path d={path} className={`fill-none ${cls}`} strokeWidth="1.5" />
        {points.map((p, i) => {
          const x = padX + (i / total) * innerW
          const y = padY + innerH - (p.v / max) * innerH
          return <circle key={i} cx={x} cy={y} r="2" className={`fill-current ${cls.replace("stroke-", "text-")}`} />
        })}
      </svg>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        {points.map((p) => (
          <span key={p.t}>{p.t.slice(5)}</span>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// Config form

function ConfigForm({ kb, onSaved }: { kb: KnowledgeBase; onSaved: () => void }) {
  const rawCfg = (kb as unknown as { governance_config?: KBGovernanceConfig | null }).governance_config
  const initial: KBGovernanceConfig = {
    expiration_threshold_days: rawCfg?.expiration_threshold_days ?? 90,
    auto_archive_idle_days: rawCfg?.auto_archive_idle_days ?? 30,
  }
  const [cfg, setCfg] = useState<KBGovernanceConfig>(initial)
  const [saving, setSaving] = useState(false)
  const dirty = cfg.expiration_threshold_days !== initial.expiration_threshold_days
    || cfg.auto_archive_idle_days !== initial.auto_archive_idle_days

  const onSave = async () => {
    setSaving(true)
    try {
      await knowledgeApi.updateGovernanceConfig(kb.id, cfg)
      toast.success("治理参数已保存")
      onSaved()
    } catch {
      toast.error("保存失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card size="sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">治理参数</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="exp-days" className="text-xs">
              过期阈值 (天)
            </Label>
            <Input
              id="exp-days"
              type="number" min={1} max={3650}
              value={cfg.expiration_threshold_days}
              onChange={(e) => setCfg({ ...cfg, expiration_threshold_days: Number(e.target.value) || 1 })}
            />
            <p className="text-[11px] text-muted-foreground">超过此天数未更新的文档计入"过期"</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="idle-days" className="text-xs">
              自动归档闲置 (天)
            </Label>
            <Input
              id="idle-days"
              type="number" min={1} max={3650}
              value={cfg.auto_archive_idle_days}
              onChange={(e) => setCfg({ ...cfg, auto_archive_idle_days: Number(e.target.value) || 1 })}
            />
            <p className="text-[11px] text-muted-foreground">冷切片闲置超过此天数时进入归档候选</p>
          </div>
        </div>
        <div>
          <Button size="sm" onClick={onSave} disabled={!dirty || saving}>
            <Save className="mr-1 size-3.5" /> 保存
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}


// ─────────────────────────────────────────────────────────────────
// Plan 35 — Retrieval Strategy Recommendations

interface RecoItem {
  query_type: string
  sample_size: number
  payload: {
    base: { bm25_weight: number; vector_weight: number; top_k: number; rerank: boolean; note: string }
    tuned: { bm25_weight: number; vector_weight: number; top_k: number; rerank: boolean; note: string }
    stats: {
      sample_size: number; hit_count: number; no_result_count: number
      avg_result_count: number; hit_rate: number
      adopted_via_events: number; adopted_rate: number
    }
    note: string
  }
  generated_at: string
}

const QTYPE_LABEL: Record<string, string> = {
  troubleshooting: "故障排查",
  concept: "概念解释",
  how_to: "操作步骤",
  definition: "术语定义",
  lookup: "精确查找",
  other: "其他",
}

function RetrievalRecoCard({ kbId }: { kbId: string }) {
  const [items, setItems] = useState<RecoItem[] | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    knowledgeApi.retrievalRecommendations(kbId)
      .then((r) => { if (!cancelled) setItems(r) })
      .catch(() => { if (!cancelled) setItems([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [kbId])

  if (loading) {
    return (
      <Card size="sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <BarChart3 className="size-4 text-primary" /> 检索策略建议
          </CardTitle>
        </CardHeader>
        <CardContent className="py-4 text-xs text-muted-foreground">加载中…</CardContent>
      </Card>
    )
  }

  if (!items || items.length === 0) {
    return (
      <Card size="sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <BarChart3 className="size-4 text-primary" /> 检索策略建议
          </CardTitle>
        </CardHeader>
        <CardContent className="py-4 text-xs text-muted-foreground">
          暂无建议数据 —— 后台每日重算；积累一定检索量后会出现按 query 类型的策略推荐
        </CardContent>
      </Card>
    )
  }

  return (
    <Card size="sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <BarChart3 className="size-4 text-primary" /> 检索策略建议（{items.length}）
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5">
        {items.map((it) => {
          const t = it.payload.tuned
          const b = it.payload.base
          const hasShift = b.bm25_weight !== t.bm25_weight || b.top_k !== t.top_k || b.rerank !== t.rerank
          return (
            <div key={it.query_type} className="rounded-md border p-2.5">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-sm font-medium">{QTYPE_LABEL[it.query_type] || it.query_type}</span>
                <Badge variant="outline" className="text-[10px]">样本 {it.sample_size}</Badge>
              </div>
              <div className="flex flex-wrap gap-1 text-[11px]">
                <Badge variant={hasShift ? "default" : "secondary"} className="font-mono">
                  BM25 {t.bm25_weight} / 向量 {t.vector_weight}
                </Badge>
                <Badge variant="outline" className="font-mono">top_k {t.top_k}</Badge>
                <Badge variant="outline" className="font-mono">{t.rerank ? "rerank ✓" : "rerank ×"}</Badge>
                {it.payload.stats.sample_size > 0 && (
                  <Badge variant="outline" className="font-mono">命中率 {(it.payload.stats.hit_rate * 100).toFixed(0)}%</Badge>
                )}
              </div>
              {it.payload.note && (
                <p className="mt-1.5 text-[11px] text-muted-foreground">{it.payload.note}</p>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
