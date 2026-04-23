import { useEffect, useState } from "react"
import { CheckCircle2, XCircle } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/api/client"

interface ObservabilityStatus {
  langfuse: {
    configured: boolean
    host: string | null
    has_public_key: boolean
    has_secret_key: boolean
    capture_io: boolean
  }
}


/**
 * Phase 1b observability page (spec 12 L83/L120, spec 05).
 *
 * Langfuse bootstrap is env-only (3 vars) per spec — we expose a read-only
 * status view rather than a form, so admins see exactly what the runtime is
 * connected to without being able to rewrite secrets through the UI.
 */
export default function ObservabilityPage() {
  const [status, setStatus] = useState<ObservabilityStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<ObservabilityStatus>("/system/observability")
      .then(setStatus)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">可观测性</h1>
        <p className="text-sm text-muted-foreground">
          Phase 1b 集成 Langfuse 作为 Trace / Span / Generation 的收集端，
          覆盖 Simple Agent、Workflow Agent、LLM 调用与跨域事件。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Langfuse 接入状态</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {loading && <p className="text-xs text-muted-foreground">加载中...</p>}
          {status && (
            <>
              <StatusRow
                label="整体状态"
                ok={status.langfuse.configured}
                text={status.langfuse.configured ? "已配置并接入" : "未配置 — 运行时使用 no-op 客户端（所有观测调用被静默跳过）"}
              />
              <StatusRow
                label="LANGFUSE_HOST"
                ok={Boolean(status.langfuse.host)}
                text={status.langfuse.host ?? "未设置"}
                mono
              />
              <StatusRow
                label="LANGFUSE_PUBLIC_KEY"
                ok={status.langfuse.has_public_key}
                text={status.langfuse.has_public_key ? "已设置" : "未设置"}
              />
              <StatusRow
                label="LANGFUSE_SECRET_KEY"
                ok={status.langfuse.has_secret_key}
                text={status.langfuse.has_secret_key ? "已设置" : "未设置"}
              />
              <StatusRow
                label="LANGFUSE_CAPTURE_IO"
                ok={status.langfuse.capture_io}
                text={status.langfuse.capture_io ? "开启（传输 prompt / 输出到 Langfuse）" : "关闭（仅传输元数据 / token 计数 / 时延，不传输原文）"}
              />
            </>
          )}

          <div className="mt-4 space-y-2 rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            <div className="font-medium text-foreground">配置方式</div>
            <p>
              在部署配置（.env 或容器环境变量）中设置以下三项：
            </p>
            <pre className="overflow-x-auto rounded bg-background p-2 font-mono text-[11px]">
{`LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
# 可选：是否上传 prompt / 输出内容（默认 false，避免 PII 泄漏）
LANGFUSE_CAPTURE_IO=false`}
            </pre>
            <p>
              设置后重启 backend 即生效。修改不需要迁移、无需停服
              Celery worker 单独重启即可。
            </p>
          </div>

          <div className="mt-4 space-y-2 rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            <div className="font-medium text-foreground">追踪层级</div>
            <pre className="overflow-x-auto rounded bg-background p-2 font-mono text-[11px]">
{`trace: agent.chat                 (Simple Agent / Workflow Agent)
  span: workflow.execute         (仅 Workflow Agent)
    span: node.<type> ...        (每节点一个)
      generation: llm.generation (LLM / Classifier / Extractor)

独立 traces (bus event relay):
  document.completed / failed
  kb.reindex_completed
  workflow.execution_completed / failed
  governance.alert`}
            </pre>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}


function StatusRow({
  label, ok, text, mono = false,
}: {
  label: string
  ok: boolean
  text: string
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b pb-2 last:border-b-0 last:pb-0">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className={`flex items-center gap-1 text-xs ${mono ? "font-mono" : ""}`}>
        {ok
          ? <CheckCircle2 className="size-3.5 text-green-600" />
          : <XCircle className="size-3.5 text-muted-foreground" />}
        <span className={ok ? "" : "text-muted-foreground"}>{text}</span>
      </span>
    </div>
  )
}
