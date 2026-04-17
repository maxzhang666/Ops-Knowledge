import { useEffect, useState } from "react"
import { Flame, Snowflake, Sparkles } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { EmptyState } from "@/components/shared/empty-state"
import { knowledgeApi, type KnowledgeBase, type QualityOverview, type KBStatus } from "@/api/knowledge"

const statusLabels: Record<KBStatus, { label: string; variant: "default" | "secondary" | "destructive" }> = {
  active: { label: "正常", variant: "default" },
  indexing: { label: "索引中", variant: "secondary" },
  error: { label: "异常", variant: "destructive" },
}

interface QualityOverviewTabProps {
  kb: KnowledgeBase
}

export function QualityOverviewTab({ kb }: QualityOverviewTabProps) {
  const [data, setData] = useState<QualityOverview | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    knowledgeApi.qualityOverview(kb.id)
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [kb.id])

  const status = statusLabels[kb.status]

  return (
    <div className="mt-4 flex flex-col gap-4">
      {/* Top stats */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="文档总数" value={String(kb.document_count)} />
        <StatCard title="分块总数" value={String(kb.chunk_count)} />
        <StatCard title="状态">
          <Badge variant={status.variant}>{status.label}</Badge>
        </StatCard>
        <StatCard title="Embedding 模型">
          <Badge variant="secondary" className="truncate">
            {kb.embedding_model_name ?? "未配置"}
          </Badge>
        </StatCard>
      </div>

      {loading ? (
        <LoadingSpinner className="py-12" />
      ) : !data || data.chunk_count === 0 ? (
        <EmptyState
          title="暂无质量数据"
          description="上传文档并处理完成后即可查看质量分布"
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Quality distribution */}
          <Card size="sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Sparkles className="size-4 text-primary" /> 切片质量分布
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {data.avg_quality != null && (
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-semibold">
                    {(data.avg_quality * 100).toFixed(1)}%
                  </span>
                  <span className="text-xs text-muted-foreground">平均质量分</span>
                </div>
              )}
              <DistributionBar
                total={data.chunk_count}
                segments={[
                  { label: "高质量 (≥80%)", value: data.quality_distribution.high, cls: "bg-success" },
                  { label: "中等 (50–80%)", value: data.quality_distribution.mid, cls: "bg-info" },
                  { label: "低质量 (<50%)", value: data.quality_distribution.low, cls: "bg-warning" },
                  { label: "未评分", value: data.quality_distribution.unscored, cls: "bg-muted-foreground/40" },
                ]}
              />
            </CardContent>
          </Card>

          {/* Retrieval heatmap */}
          <Card size="sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Flame className="size-4 text-warning" /> 检索热度
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <div className="grid grid-cols-3 gap-2">
                <MetricCell label="总命中次数" value={data.total_hits} />
                <MetricCell label="有命中切片" value={data.hit_chunk_count} />
                <MetricCell
                  label="冷切片"
                  value={data.cold_chunk_count}
                  hint={<Snowflake className="ml-1 inline size-3 text-muted-foreground" />}
                />
              </div>
              {data.cold_chunk_count > 0 && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {((data.cold_chunk_count / data.chunk_count) * 100).toFixed(0)}% 切片尚未被检索到；可考虑调整分片或上传更多多样化查询来暖化索引
                </p>
              )}
            </CardContent>
          </Card>

          {/* Top hits */}
          {data.top_hit_chunks.length > 0 && (
            <Card size="sm" className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-sm">热门切片（Top {data.top_hit_chunks.length}）</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-xs">
                {data.top_hit_chunks.map((c, i) => (
                  <div key={c.id} className="flex items-start gap-2 rounded-md border p-2">
                    <Badge variant="outline" className="shrink-0">#{i + 1}</Badge>
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-muted-foreground">{c.preview}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="font-semibold">{c.hit_count}</p>
                      <p className="text-[10px] text-muted-foreground">命中</p>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

function StatCard({ title, value, children }: { title: string; value?: string; children?: React.ReactNode }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-sm font-normal text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {value ? <p className="text-2xl font-semibold">{value}</p> : children}
      </CardContent>
    </Card>
  )
}

function DistributionBar({
  total, segments,
}: {
  total: number
  segments: Array<{ label: string; value: number; cls: string }>
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        {segments.map((s) => {
          const pct = total > 0 ? (s.value / total) * 100 : 0
          if (pct === 0) return null
          return <div key={s.label} className={s.cls} style={{ width: `${pct}%` }} title={`${s.label}: ${s.value}`} />
        })}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center gap-1.5">
            <span className={`size-2 shrink-0 rounded-sm ${s.cls}`} />
            <span className="flex-1 truncate text-muted-foreground">{s.label}</span>
            <span className="font-medium">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function MetricCell({ label, value, hint }: { label: string; value: number; hint?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border p-2">
      <p className="text-lg font-semibold">
        {value}{hint}
      </p>
      <p className="text-[10px] text-muted-foreground">{label}</p>
    </div>
  )
}
