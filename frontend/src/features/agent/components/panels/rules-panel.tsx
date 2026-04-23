import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Plus, Pencil, Trash2, ArrowUp, ArrowDown, Loader2,
} from "lucide-react"
import { toast } from "sonner"

import type { Agent } from "@/api/agent"
import {
  orchestratorApi,
  type AgentRule,
  type CreateRulePayload,
  type MatchType,
} from "@/api/orchestrator"
import { workflowApi, type WorkflowSummary } from "@/api/workflow"
// memory:feedback_dropdown_display_label — 规则表显示 Workflow 名字不是 uuid
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { RuleEditorDialog } from "./rules-editor/rule-editor-dialog"

const MATCH_LABEL: Record<MatchType, string> = {
  condition: "条件",
  keyword: "关键词",
  regex: "正则",
  llm_intent: "LLM 意图",
}


/**
 * Orchestrator 规则表面板（Plan 31 N2.2）。
 *
 * 每行展示：优先级 / 匹配类型 / 匹配摘要 / handler / 命中次数 /
 * 最近命中 / 平均延迟 / 激活开关 / 操作。
 *
 * 排序用上下箭头调 moveRule(after_rule_id) —— 服务端算中位数 priority
 * (Plan 31 B5)，前端不用关心精度。N3 再升级为拖拽。
 */
export function RulesPanel({ agent, onUpdated }: { agent: Agent; onUpdated?: () => void }) {
  const [rules, setRules] = useState<AgentRule[]>([])
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [editingRule, setEditingRule] = useState<AgentRule | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [movingId, setMovingId] = useState<string | null>(null)

  const workflowById = useMemo(() => {
    const m = new Map<string, WorkflowSummary>()
    for (const w of workflows) m.set(w.id, w)
    return m
  }, [workflows])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rows, wfs] = await Promise.all([
        orchestratorApi.listRules(agent.id),
        workflowApi.list().catch(() => [] as WorkflowSummary[]),
      ])
      setRules(Array.isArray(rows) ? rows : [])
      setWorkflows(Array.isArray(wfs) ? wfs : (wfs as { items?: WorkflowSummary[] }).items ?? [])
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载规则失败")
    } finally {
      setLoading(false)
    }
  }, [agent.id])

  useEffect(() => { load() }, [load])

  const sorted = useMemo(
    () => [...rules].sort((a, b) => a.priority - b.priority),
    [rules],
  )

  function openCreate() {
    setEditingRule(null)
    setDialogOpen(true)
  }

  function openEdit(r: AgentRule) {
    setEditingRule(r)
    setDialogOpen(true)
  }

  async function handleSave(payload: CreateRulePayload) {
    try {
      if (editingRule) {
        await orchestratorApi.updateRule(agent.id, editingRule.id, payload)
        toast.success("规则已更新")
      } else {
        await orchestratorApi.createRule(agent.id, payload)
        toast.success("规则已创建")
      }
      setDialogOpen(false)
      await load()
      onUpdated?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败")
      throw e  // 让 dialog 保持打开
    }
  }

  async function handleToggle(rule: AgentRule) {
    try {
      const updated = await orchestratorApi.updateRule(agent.id, rule.id, {
        is_active: !rule.is_active,
      })
      setRules((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "更新失败")
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await orchestratorApi.deleteRule(agent.id, deleteTarget)
      setRules((prev) => prev.filter((r) => r.id !== deleteTarget))
      toast.success("已删除")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败")
    }
  }

  async function handleMoveUp(rule: AgentRule) {
    const idx = sorted.findIndex((r) => r.id === rule.id)
    if (idx <= 0) return
    // Move above current upper neighbor = "after the rule that comes before upper"
    const targetAfter = idx >= 2 ? sorted[idx - 2].id : null  // null ⇒ top
    setMovingId(rule.id)
    try {
      await orchestratorApi.moveRule(agent.id, rule.id, targetAfter)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "移动失败")
    } finally {
      setMovingId(null)
    }
  }

  async function handleMoveDown(rule: AgentRule) {
    const idx = sorted.findIndex((r) => r.id === rule.id)
    if (idx < 0 || idx >= sorted.length - 1) return
    const targetAfter = sorted[idx + 1].id  // move to just after current lower neighbor
    setMovingId(rule.id)
    try {
      await orchestratorApi.moveRule(agent.id, rule.id, targetAfter)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "移动失败")
    } finally {
      setMovingId(null)
    }
  }

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">路由规则</h2>
          <p className="text-xs text-muted-foreground">
            按优先级从上到下评估；第一个匹配的规则决定派发对象
          </p>
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="mr-1 size-3.5" /> 新建规则
        </Button>
      </div>

      {sorted.length === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          还没有规则。点击"新建规则"开始配置。
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-xs">
            <thead className="border-b bg-muted/40 text-left text-muted-foreground">
              <tr>
                <th className="w-10 px-2 py-2 text-center">#</th>
                <th className="w-20 px-2 py-2">匹配</th>
                <th className="px-2 py-2">规则摘要</th>
                <th className="px-2 py-2">派发</th>
                <th className="w-16 px-2 py-2 text-right">命中</th>
                <th className="w-28 px-2 py-2">最近命中</th>
                <th className="w-16 px-2 py-2 text-right">均耗</th>
                <th className="w-14 px-2 py-2 text-center">启用</th>
                <th className="w-24 px-2 py-2 text-center">操作</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, idx) => (
                <tr key={r.id} className="border-b last:border-b-0 hover:bg-muted/20">
                  <td className="px-2 py-2 text-center text-muted-foreground">{idx + 1}</td>
                  <td className="px-2 py-2">
                    <Badge variant="secondary">{MATCH_LABEL[r.match_type]}</Badge>
                  </td>
                  <td className="px-2 py-2">
                    <span className="font-mono text-[11px]">{summarizeMatch(r)}</span>
                  </td>
                  <td className="px-2 py-2">
                    {/* memory:feedback_dropdown_display_label — 显示 Workflow 名字不是 uuid */}
                    <span className="truncate">
                      {r.handler_id
                        ? (workflowById.get(r.handler_id)?.name ?? `<unknown ${r.handler_id.slice(0, 8)}…>`)
                        : "-"}
                    </span>
                    <div className="text-[10px] text-muted-foreground">Workflow</div>
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">{r.hit_count}</td>
                  <td className="px-2 py-2 text-[11px] text-muted-foreground">
                    {r.last_hit_at ? new Date(r.last_hit_at).toLocaleString("zh-CN") : "-"}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">
                    {r.avg_latency_ms != null ? `${r.avg_latency_ms}ms` : "-"}
                  </td>
                  <td className="px-2 py-2 text-center">
                    <Switch
                      checked={r.is_active}
                      onCheckedChange={() => handleToggle(r)}
                    />
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex items-center justify-center gap-0.5">
                      <Button
                        variant="ghost" size="icon"
                        className="size-7"
                        onClick={() => handleMoveUp(r)}
                        disabled={idx === 0 || movingId === r.id}
                      >
                        {movingId === r.id ? <Loader2 className="size-3 animate-spin" /> : <ArrowUp className="size-3" />}
                      </Button>
                      <Button
                        variant="ghost" size="icon"
                        className="size-7"
                        onClick={() => handleMoveDown(r)}
                        disabled={idx === sorted.length - 1 || movingId === r.id}
                      >
                        <ArrowDown className="size-3" />
                      </Button>
                      <Button variant="ghost" size="icon" className="size-7" onClick={() => openEdit(r)}>
                        <Pencil className="size-3" />
                      </Button>
                      <Button variant="ghost" size="icon" className="size-7" onClick={() => setDeleteTarget(r.id)}>
                        <Trash2 className="size-3" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <RuleEditorDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editingRule={editingRule}
        agent={agent}
        onSave={handleSave}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除规则"
        description="确认删除此条规则？历史命中记录会保留但后续不再命中此规则。"
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}


// ─── Summary helper ───

function summarizeMatch(r: AgentRule): string {
  const cfg = r.match_config as Record<string, unknown>
  if (r.match_type === "keyword") {
    const list = (cfg.any_of as string[]) ?? []
    return list.map((k) => `"${k}"`).join(" / ") || "(空)"
  }
  if (r.match_type === "regex") {
    return `/${cfg.pattern}/${cfg.flags ?? ""}`
  }
  if (r.match_type === "condition") {
    return `${cfg.path} ${cfg.op} ${JSON.stringify(cfg.value)}`
  }
  if (r.match_type === "llm_intent") {
    return `category = "${cfg.category}"`
  }
  return JSON.stringify(cfg)
}
