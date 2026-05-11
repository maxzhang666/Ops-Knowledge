import type { CSSProperties } from "react"
import { useNavigate } from "react-router-dom"
import { AlertTriangle, Download, MoreHorizontal, Settings2, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { TimeDisplay } from "@/components/shared/time-display"
import { knowledgeApi, type KBSourceType, type KBStatus, type KnowledgeBase } from "@/api/knowledge"
import { cn } from "@/lib/utils"

const statusLabel: Record<KBStatus, string> = {
  active: "正常",
  indexing: "索引中",
  error: "异常",
}

const SOURCE_TYPE_CHIP: Record<KBSourceType, { icon: string; label: string }> = {
  file: { icon: "📁", label: "文件" },
  entry: { icon: "📋", label: "条目" },
  git_repo: { icon: "💻", label: "代码" },
  confluence: { icon: "🔗", label: "同步" },
}

interface KBCardProps {
  kb: KnowledgeBase
  onDelete: (kb: KnowledgeBase) => void
}

async function handleExport(kb: KnowledgeBase) {
  try {
    const blob = await knowledgeApi.exportKB(kb.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${kb.name}.oka`
    a.click()
    URL.revokeObjectURL(url)
    toast.success(`已导出 ${kb.name}.oka`)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "导出失败")
  }
}

// ── 健康档语义 ───────────────────────────────────────────
// 左上斜切色块的颜色与字符均由 health_score 派生，让色块本身传递语义
// （绿=健康 / 黄=普通 / 红=低 / 灰=尚未计算）。状态异常优先级最高。

type HealthTier = "high" | "mid" | "low" | "none" | "error"

function getHealthTier(kb: KnowledgeBase): HealthTier {
  if (kb.status === "error") return "error"
  if (kb.health_score === null) return "none"
  if (kb.health_score >= 80) return "high"
  if (kb.health_score >= 40) return "mid"
  return "low"
}

const wedgeGradient: Record<HealthTier, string> = {
  // 绿色（success-ish），略带饱和差
  high: "linear-gradient(135deg, oklch(0.65 0.16 155) 0%, oklch(0.50 0.14 170) 100%)",
  // 琥珀（warning-ish）
  mid: "linear-gradient(135deg, oklch(0.78 0.16 85) 0%, oklch(0.65 0.18 60) 100%)",
  // 红色（low health，仍区别于 error 斜纹）
  low: "linear-gradient(135deg, oklch(0.65 0.20 25) 0%, oklch(0.52 0.22 10) 100%)",
  // 灰（尚未计算）
  none: "linear-gradient(135deg, oklch(0.70 0 0) 0%, oklch(0.55 0 0) 100%)",
  // error 用 destructive 斜纹（与 low 视觉区隔，提示"系统异常"≠"治理低分"）
  error:
    "repeating-linear-gradient(135deg, var(--destructive) 0 8px, color-mix(in oklab, var(--destructive) 60%, transparent) 8px 14px)",
}

function getWedgeText(kb: KnowledgeBase, tier: HealthTier): string {
  if (tier === "error") return "" // 让位 ⚠ 角标
  if (tier === "none") return "—"
  return String(kb.health_score)
}

function getWedgeTooltip(kb: KnowledgeBase, tier: HealthTier): string {
  if (tier === "error") return "知识库异常"
  if (tier === "none") return "治理健康分尚未计算（首次每日任务或访问治理面板后填充）"
  return `治理健康分 ${kb.health_score} / 100`
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-base font-semibold tabular-nums">{value}</span>
      <span className="text-[10px] text-muted-foreground">{label}</span>
    </div>
  )
}

export function KBCard({ kb, onDelete }: KBCardProps) {
  const navigate = useNavigate()
  const tier = getHealthTier(kb)
  const wedgeText = getWedgeText(kb, tier)

  const wedgeStyle: CSSProperties = {
    clipPath: "polygon(0 0, 100% 0, 0 100%)",
    backgroundImage: wedgeGradient[tier],
  }

  return (
    <Card
      className="group relative cursor-pointer overflow-hidden transition-shadow hover:shadow-elevation-2"
      onClick={() => navigate(`/knowledge/${kb.id}`)}
    >
      <div
        className={cn(
          "absolute left-0 top-0 size-16",
          kb.status === "indexing" && "animate-pulse",
        )}
        title={getWedgeTooltip(kb, tier)}
      >
        <div className="absolute inset-0" style={wedgeStyle} />
        {wedgeText && (
          <span
            className={cn(
              "absolute left-2 top-1 font-bold leading-none text-white/90 tabular-nums",
              wedgeText.length === 3 ? "text-base" : "text-[22px]",
            )}
            style={{ textShadow: "0 1px 2px rgba(0,0,0,0.25)" }}
          >
            {wedgeText}
          </span>
        )}
        {tier === "error" && (
          <AlertTriangle
            className="absolute right-1 top-1 size-3 text-white"
            style={{ filter: "drop-shadow(0 1px 1px rgba(0,0,0,0.3))" }}
          />
        )}
      </div>

      <CardHeader className="pl-20">
        <div className="flex items-start gap-2">
          <CardTitle className="min-w-0 flex-1 truncate">{kb.name}</CardTitle>
          {SOURCE_TYPE_CHIP[kb.source_type] && (
            <span
              className="inline-flex shrink-0 items-center gap-1 rounded border bg-muted/40 px-1.5 py-0.5 text-[10px] text-muted-foreground"
              title={`知识库类型：${SOURCE_TYPE_CHIP[kb.source_type].label}`}
            >
              <span>{SOURCE_TYPE_CHIP[kb.source_type].icon}</span>
              <span>{SOURCE_TYPE_CHIP[kb.source_type].label}</span>
            </span>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  className="inline-flex size-7 shrink-0 items-center justify-center rounded opacity-0 transition-opacity hover:bg-accent group-hover:opacity-100 data-[state=open]:opacity-100"
                  title="操作"
                  onClick={(e) => e.stopPropagation()}
                />
              }
            >
              <MoreHorizontal className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="text-sm" onClick={(e) => e.stopPropagation()}>
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  navigate(`/knowledge/${kb.id}?tab=config`)
                }}
              >
                <Settings2 className="mr-2 size-3.5" /> 配置
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  handleExport(kb)
                }}
              >
                <Download className="mr-2 size-3.5" /> 导出 .oka
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(kb)
                }}
                className="text-destructive"
              >
                <Trash2 className="mr-2 size-3.5" /> 删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        {kb.description && (
          <CardDescription className="line-clamp-2">{kb.description}</CardDescription>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 items-center gap-2">
          <Metric value={kb.document_count.toLocaleString()} label="文档" />
          <Metric value={kb.chunk_count.toLocaleString()} label="分块" />
        </div>

        <div className="flex items-center gap-1.5 border-t pt-2 text-xs text-muted-foreground">
          <span className="min-w-0 truncate">{kb.embedding_model_name ?? "未配置"}</span>
          <span>·</span>
          <span
            className={cn(
              "shrink-0",
              kb.status === "error" && "font-medium text-destructive",
              kb.status === "indexing" && "text-warning",
            )}
          >
            {statusLabel[kb.status]}
          </span>
          <span className="ml-auto shrink-0 whitespace-nowrap">
            <TimeDisplay value={kb.updated_at} />
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
