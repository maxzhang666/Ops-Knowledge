/**
 * LLM 意图分类器配置 + 测试（Plan 31 N2.4）。
 *
 * 分类器是 Orchestrator Agent 的 opt-in 配置：不配也能跑（只支持
 * keyword/regex/condition 路由）。配了之后才能新建 llm_intent 规则。
 *
 * 信任白名单也在这里维护 —— 条件规则能匹配哪些 metadata 字段，
 * 运营完全可见 + 可调整（默认 3 个 user.* 路径）。
 */
import { useCallback, useEffect, useState } from "react"
import { Loader2, Plus, Trash2, CheckCircle2, XCircle } from "lucide-react"
import { toast } from "sonner"

import type { Agent } from "@/api/agent"
import {
  orchestratorApi,
  type ClassifierCategory,
  type DefaultHandler,
  type OrchestratorConfig,
} from "@/api/orchestrator"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { ModelRegistryPicker } from "@/features/workflow/editors/pickers"


const DEFAULT_TRUSTED = ["user.role", "user.department_id", "user.id"]


export function ClassifierPanel({ agent, onUpdated }: { agent: Agent; onUpdated?: () => void }) {
  const existing = (agent.orchestrator_config as OrchestratorConfig | null) ?? null
  const [modelId, setModelId] = useState<string>(
    (existing?.classifier?.model_registry_id as string) ?? "",
  )
  const [categories, setCategories] = useState<ClassifierCategory[]>(
    existing?.classifier?.categories ?? [],
  )
  const [threshold, setThreshold] = useState<number>(
    existing?.classifier?.confidence_threshold ?? 0.6,
  )
  const [cacheTtl, setCacheTtl] = useState<number>(
    existing?.classifier?.cache_ttl_seconds ?? 300,
  )
  const [trustedPaths, setTrustedPaths] = useState<string[]>(
    existing?.trusted_metadata_paths ?? DEFAULT_TRUSTED,
  )

  const [saving, setSaving] = useState(false)
  const [probeText, setProbeText] = useState("")
  const [probeResult, setProbeResult] = useState<{ ok: boolean; text: string } | null>(null)
  const [probing, setProbing] = useState(false)

  const addCategory = useCallback(() => {
    setCategories((prev) => [...prev, { name: "", description: "", examples: [] }])
  }, [])
  const updateCategory = (idx: number, patch: Partial<ClassifierCategory>) => {
    setCategories((prev) => prev.map((c, i) => (i === idx ? { ...c, ...patch } : c)))
  }
  const removeCategory = (idx: number) => setCategories((prev) => prev.filter((_, i) => i !== idx))

  async function handleSave() {
    if (!existing?.default_handler) {
      toast.error("请先通过创建 Orchestrator Agent 初始化 default_handler（此字段在 Agent 创建时配置）")
      return
    }
    setSaving(true)
    try {
      const payload: OrchestratorConfig = {
        default_handler: existing.default_handler as DefaultHandler,
        trusted_metadata_paths: trustedPaths.filter(Boolean),
        diagnostic_mode_allowed_roles:
          existing?.diagnostic_mode_allowed_roles ?? ["system_admin", "dept_admin"],
        classifier: modelId && categories.length > 0 ? {
          model_registry_id: modelId,
          categories: categories.filter((c) => c.name.trim()),
          confidence_threshold: threshold,
          cache_ttl_seconds: cacheTtl,
          fallback_on_low_confidence: "default",
        } : null,
      }
      await orchestratorApi.updateConfig(agent.id, payload)
      toast.success("分类器配置已保存")
      onUpdated?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  async function handleProbe() {
    if (!probeText.trim()) return
    setProbing(true)
    setProbeResult(null)
    try {
      const r = await orchestratorApi.testClassifier(agent.id, probeText)
      setProbeResult({
        ok: r.category !== "__unknown__",
        text: `category=${r.category} · confidence=${r.confidence.toFixed(2)}${r.cached ? " (cached)" : ""}`,
      })
    } catch (e) {
      setProbeResult({ ok: false, text: e instanceof Error ? e.message : "测试失败" })
    } finally {
      setProbing(false)
    }
  }

  return (
    <div className="flex flex-col gap-5 p-4">
      {/* Classifier */}
      <section className="rounded-lg border p-4">
        <div className="mb-3">
          <h3 className="text-sm font-semibold">LLM 意图分类器</h3>
          <p className="text-xs text-muted-foreground">
            可选。配置后才能创建 <code className="rounded bg-muted px-1">llm_intent</code> 规则。
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Label className="text-xs">分类模型</Label>
            <ModelRegistryPicker value={modelId} kind="llm" onChange={setModelId} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1">
              <Label className="text-xs">置信度阈值</Label>
              <Input
                type="number" step="0.05" min={0} max={1}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value) || 0)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs">缓存 TTL（秒）</Label>
              <Input
                type="number" min={0} max={86400}
                value={cacheTtl}
                onChange={(e) => setCacheTtl(Number(e.target.value) || 0)}
              />
            </div>
          </div>
        </div>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between">
            <Label className="text-xs">类别</Label>
            <Button variant="ghost" size="sm" onClick={addCategory}>
              <Plus className="mr-1 size-3" /> 添加类别
            </Button>
          </div>
          {categories.length === 0 ? (
            <p className="text-xs text-muted-foreground">未定义类别。至少添加一项才能使用 llm_intent 规则。</p>
          ) : (
            <div className="flex flex-col gap-2">
              {categories.map((c, i) => (
                <div key={i} className="rounded border bg-muted/10 p-2">
                  <div className="flex items-start gap-2">
                    <Input
                      className="h-7 w-40 text-xs"
                      value={c.name}
                      onChange={(e) => updateCategory(i, { name: e.target.value })}
                      placeholder="product_question"
                    />
                    <Input
                      className="h-7 flex-1 text-xs"
                      value={c.description ?? ""}
                      onChange={(e) => updateCategory(i, { description: e.target.value })}
                      placeholder="产品功能/用法咨询"
                    />
                    <Button variant="ghost" size="icon" className="size-7" onClick={() => removeCategory(i)}>
                      <Trash2 className="size-3" />
                    </Button>
                  </div>
                  <Textarea
                    className="mt-1.5 h-16 text-xs"
                    placeholder="示例（每行一条，帮助分类器提高准确率）"
                    value={(c.examples ?? []).join("\n")}
                    onChange={(e) => updateCategory(i, {
                      examples: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean),
                    })}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Probe */}
        {modelId && categories.length > 0 && (
          <div className="mt-4 rounded border border-dashed bg-muted/10 p-3">
            <Label className="text-xs">测试分类</Label>
            <div className="mt-1 flex gap-2">
              <Input
                className="h-8 text-xs"
                value={probeText}
                onChange={(e) => setProbeText(e.target.value)}
                placeholder="输入一段用户消息..."
              />
              <Button size="sm" onClick={handleProbe} disabled={probing || !probeText.trim()}>
                {probing ? <Loader2 className="size-3.5 animate-spin" /> : "分类"}
              </Button>
            </div>
            {probeResult && (
              <div className={`mt-2 flex items-center gap-1 text-xs ${probeResult.ok ? "text-green-600" : "text-muted-foreground"}`}>
                {probeResult.ok ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
                {probeResult.text}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Trusted metadata paths */}
      <section className="rounded-lg border p-4">
        <h3 className="mb-1 text-sm font-semibold">可信 metadata 字段白名单</h3>
        <p className="mb-3 text-xs text-muted-foreground">
          condition 规则只能匹配这里列出的字段。系统注入的字段（如 user.role
          从 JWT 自动填充）调用方无法伪造。新增自定义受信字段需要先在后端
          注入（通常需要开发配合）。
        </p>
        <div className="flex flex-col gap-1">
          {trustedPaths.map((p, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input
                className="h-7 flex-1 font-mono text-xs"
                value={p}
                onChange={(e) => setTrustedPaths((prev) => prev.map((pp, idx) => (idx === i ? e.target.value : pp)))}
              />
              <Button
                variant="ghost" size="icon" className="size-7"
                onClick={() => setTrustedPaths((prev) => prev.filter((_, idx) => idx !== i))}
              >
                <Trash2 className="size-3" />
              </Button>
            </div>
          ))}
          <Button
            variant="ghost" size="sm"
            onClick={() => setTrustedPaths((prev) => [...prev, ""])}
          >
            <Plus className="mr-1 size-3" /> 添加路径
          </Button>
        </div>
      </section>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "保存中..." : "保存配置"}
        </Button>
      </div>
    </div>
  )
}
