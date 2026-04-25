import { useEffect, useMemo, useState } from "react"
import {
  ActivitySquare, BarChart3, Coins, Cpu, Layers, Loader2, Users,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { systemApi } from "@/api/system"

/**
 * 成本面板（Plan 28 M3）—— 系统管理员专用：
 *  - 顶部 4 卡：总成本 / 总 token / 调用次数 / 平均每千 token 成本
 *  - 7 日趋势 sparkline
 *  - Top N 表（按 Provider / Model / 用户 / 调用类型 切换）
 */

type GroupBy = "provider" | "model" | "user" | "call_type"

const GROUP_META: Record<GroupBy, { label: string; icon: typeof Cpu }> = {
  provider: { label: "Provider", icon: Cpu },
  model: { label: "模型", icon: Layers },
  user: { label: "用户", icon: Users },
  call_type: { label: "调用类型", icon: ActivitySquare },
}

export default function CostsPage() {
  const [windowDays, setWindowDays] = useState(30)
  const [summary, setSummary] = useState<{
    total_cost: number
    total_input_tokens: number
    total_output_tokens: number
    call_count: number
  } | null>(null)
  const [timeline, setTimeline] = useState<Array<{ date: string; cost: number; tokens: number; calls: number }>>([])
  const [topItems, setTopItems] = useState<Record<GroupBy, Array<{ key: string; label: string; cost: number; tokens: number; calls: number }>>>({
    provider: [], model: [], user: [], call_type: [],
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([
      systemApi.costSummary(windowDays),
      systemApi.costTimeline(7),
      systemApi.costTop("provider", windowDays, 10),
      systemApi.costTop("model", windowDays, 10),
      systemApi.costTop("user", windowDays, 10),
      systemApi.costTop("call_type", windowDays, 10),
    ])
      .then(([s, t, p, m, u, c]) => {
        if (cancelled) return
        setSummary(s)
        setTimeline(t.points)
        setTopItems({
          provider: p.items,
          model: m.items,
          user: u.items,
          call_type: c.items,
        })
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [windowDays])

  const totalTokens = (summary?.total_input_tokens ?? 0) + (summary?.total_output_tokens ?? 0)
  const costPer1K = totalTokens > 0
    ? ((summary?.total_cost ?? 0) / (totalTokens / 1000))
    : 0

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">成本</h1>
          <p className="text-xs text-muted-foreground">基于 LiteLLM 价格表估算的真实 LLM/Embedding/Rerank 调用成本（USD）</p>
        </div>
        <Select value={String(windowDays)} onValueChange={(v) => v && setWindowDays(Number(v))}>
          <SelectTrigger className="w-32">
            {windowDays
              ? <span>近 {windowDays} 天</span>
              : <SelectValue />}
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">近 7 天</SelectItem>
            <SelectItem value="30">近 30 天</SelectItem>
            <SelectItem value="90">近 90 天</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> 加载中…
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard
              icon={Coins}
              label="总成本"
              value={`$${(summary?.total_cost ?? 0).toFixed(4)}`}
              hint={`${summary?.call_count ?? 0} 次调用`}
            />
            <SummaryCard
              icon={Layers}
              label="总 token"
              value={totalTokens.toLocaleString()}
              hint={`输入 ${(summary?.total_input_tokens ?? 0).toLocaleString()} / 输出 ${(summary?.total_output_tokens ?? 0).toLocaleString()}`}
            />
            <SummaryCard
              icon={ActivitySquare}
              label="调用次数"
              value={(summary?.call_count ?? 0).toLocaleString()}
            />
            <SummaryCard
              icon={BarChart3}
              label="每千 token 成本"
              value={`$${costPer1K.toFixed(4)}`}
              hint={totalTokens === 0 ? "暂无数据" : "USD / 1k tokens"}
            />
          </div>

          {/* Timeline */}
          <Card size="sm">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <BarChart3 className="size-4 text-primary" /> 7 日趋势
              </CardTitle>
            </CardHeader>
            <CardContent>
              <CostSparkline points={timeline} />
            </CardContent>
          </Card>

          {/* Top breakdown */}
          <Tabs defaultValue="provider">
            <TabsList variant="line">
              {(Object.keys(GROUP_META) as GroupBy[]).map((k) => (
                <TabsTrigger key={k} value={k}>{GROUP_META[k].label}</TabsTrigger>
              ))}
            </TabsList>
            {(Object.keys(GROUP_META) as GroupBy[]).map((k) => (
              <TabsContent key={k} value={k} className="mt-3">
                <TopTable items={topItems[k]} />
              </TabsContent>
            ))}
          </Tabs>
        </>
      )}
    </div>
  )
}

function SummaryCard({
  icon: Icon, label, value, hint,
}: {
  icon: typeof Coins; label: string; value: string; hint?: string
}) {
  return (
    <Card size="sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
          <Icon className="size-3.5" /> {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold">{value}</p>
        {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}

function CostSparkline({ points }: { points: Array<{ date: string; cost: number; calls: number }> }) {
  const max = useMemo(() => Math.max(0.0001, ...points.map((p) => p.cost)), [points])
  if (points.length === 0) {
    return <p className="text-xs text-muted-foreground">无数据</p>
  }
  const w = 720
  const h = 60
  const padX = 4
  const padY = 4
  const innerW = w - padX * 2
  const innerH = h - padY * 2
  const total = Math.max(1, points.length - 1)
  const path = points
    .map((p, i) => {
      const x = padX + (i / total) * innerW
      const y = padY + innerH - (p.cost / max) * innerH
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
  return (
    <div className="flex flex-col gap-1">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-16 w-full">
        <path d={path} className="fill-none stroke-primary" strokeWidth="1.5" />
        {points.map((p, i) => {
          const x = padX + (i / total) * innerW
          const y = padY + innerH - (p.cost / max) * innerH
          return <circle key={i} cx={x} cy={y} r="2" className="fill-primary" />
        })}
      </svg>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        {points.map((p) => (
          <span key={p.date}>{p.date.slice(5)}</span>
        ))}
      </div>
    </div>
  )
}

function TopTable({ items }: {
  items: Array<{ key: string; label: string; cost: number; tokens: number; calls: number }>
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-lg border p-6 text-center text-sm text-muted-foreground">
        无数据
      </div>
    )
  }
  const maxCost = items[0]?.cost ?? 0
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/40 text-left text-xs font-medium text-muted-foreground">
            <th className="px-3 py-2">名称</th>
            <th className="px-3 py-2 text-right">成本 (USD)</th>
            <th className="px-3 py-2 text-right">Token</th>
            <th className="px-3 py-2 text-right">调用次数</th>
            <th className="px-3 py-2 w-32">占比</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => {
            const pct = maxCost > 0 ? (row.cost / maxCost) * 100 : 0
            return (
              <tr key={row.key} className="border-b last:border-b-0 hover:bg-muted/30">
                <td className="px-3 py-2 font-medium" title={row.key}>
                  {row.label}
                </td>
                <td className="px-3 py-2 text-right font-mono">${row.cost.toFixed(4)}</td>
                <td className="px-3 py-2 text-right font-mono">{row.tokens.toLocaleString()}</td>
                <td className="px-3 py-2 text-right">
                  <Badge variant="outline" className="text-[10px]">{row.calls}</Badge>
                </td>
                <td className="px-3 py-2">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
