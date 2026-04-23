/**
 * 规则新建/编辑对话框（Plan 31 N2 — workflow-only scope）。
 *
 * Orchestrator Agent 的 handler_type 只有 workflow：一条规则 = 一条入口
 * 条件 → 派发到某个 Workflow SOP。其他 handler 类型（simple_agent /
 * mcp_tool / sub_agent）在协议层保留，但 UI 不暴露（spec 04 §Plan 31 scope）。
 *
 * condition 规则强制 form-based（path 下拉 + op 下拉 + value 输入），
 * 运营用户绝不写 JSONLogic 文本。
 */
import { useEffect, useMemo, useState } from "react"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger,
} from "@/components/ui/select"

import type { Agent } from "@/api/agent"
import type {
  AgentRule, CreateRulePayload, MatchType, OnHandlerError,
} from "@/api/orchestrator"

import { ConditionEditor } from "./condition-editor"
import { KeywordEditor } from "./keyword-editor"
import { RegexEditor } from "./regex-editor"
import { LLMIntentEditor } from "./llm-intent-editor"
import { WorkflowHandlerEditor } from "./handler-editor"

interface Props {
  open: boolean
  onOpenChange: (v: boolean) => void
  editingRule: AgentRule | null
  agent: Agent
  onSave: (payload: CreateRulePayload) => Promise<void>
}

const MATCH_TYPE_LABEL: Record<MatchType, string> = {
  condition: "条件（metadata 表达式）",
  keyword: "关键词",
  regex: "正则",
  llm_intent: "LLM 意图分类",
}

const ON_ERROR_LABEL: Record<OnHandlerError, string> = {
  use_default: "走默认 Workflow（推荐）",
  fallback_next: "继续尝试下一条规则",
  return_error: "直接返回错误给用户",
}


export function RuleEditorDialog({ open, onOpenChange, editingRule, agent, onSave }: Props) {
  const isEdit = editingRule !== null

  const [matchType, setMatchType] = useState<MatchType>("keyword")
  const [matchConfig, setMatchConfig] = useState<Record<string, unknown>>({})
  const [handlerId, setHandlerId] = useState<string | null>(null)
  const [handlerConfig, setHandlerConfig] = useState<Record<string, unknown>>({
    input_mapping: { query: "$message" },
  })
  const [onError, setOnError] = useState<OnHandlerError>("use_default")
  const [active, setActive] = useState(true)
  const [saving, setSaving] = useState(false)

  const orchCfg = (agent.orchestrator_config ?? {}) as Record<string, unknown>
  const trustedPaths = useMemo(
    () => ((orchCfg.trusted_metadata_paths as string[]) ?? ["user.role", "user.department_id", "user.id"]),
    [orchCfg],
  )
  const classifierCategories = useMemo(() => {
    const c = orchCfg.classifier as { categories?: { name: string; description?: string }[] } | undefined
    return c?.categories ?? []
  }, [orchCfg])

  useEffect(() => {
    if (!open) return
    if (editingRule) {
      setMatchType(editingRule.match_type)
      setMatchConfig(editingRule.match_config)
      setHandlerId(editingRule.handler_id)
      setHandlerConfig(editingRule.handler_config ?? { input_mapping: { query: "$message" } })
      setOnError(editingRule.on_handler_error)
      setActive(editingRule.is_active)
    } else {
      setMatchType("keyword")
      setMatchConfig({ any_of: [], case_sensitive: false })
      setHandlerId(null)
      setHandlerConfig({ input_mapping: { query: "$message" } })
      setOnError("use_default")
      setActive(true)
    }
  }, [open, editingRule])

  function handleMatchTypeChange(v: MatchType) {
    setMatchType(v)
    if (v === "keyword") setMatchConfig({ any_of: [], case_sensitive: false })
    else if (v === "regex") setMatchConfig({ pattern: "", flags: "" })
    else if (v === "condition") setMatchConfig({ path: trustedPaths[0] ?? "", op: "==", value: "" })
    else if (v === "llm_intent") setMatchConfig({ category: classifierCategories[0]?.name ?? "" })
  }

  async function handleSubmit() {
    setSaving(true)
    try {
      await onSave({
        match_type: matchType,
        match_config: matchConfig,
        handler_type: "workflow",
        handler_id: handlerId,
        handler_config: handlerConfig,
        on_handler_error: onError,
        is_active: active,
      })
    } catch {
      /* parent toasts */
    } finally {
      setSaving(false)
    }
  }

  const canSubmit = !saving && _isValid(matchType, matchConfig, handlerId)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑规则" : "新建规则"}</DialogTitle>
          <DialogDescription>
            条件命中 → 派发到 Workflow SOP；运行时按优先级评估
          </DialogDescription>
        </DialogHeader>

        <div className="flex max-h-[65vh] flex-col gap-4 overflow-y-auto pr-1">
          {/* Match type */}
          <div className="flex flex-col gap-2">
            <Label className="text-xs">匹配类型</Label>
            <Select value={matchType} onValueChange={(v) => v && handleMatchTypeChange(v as MatchType)}>
              <SelectTrigger>
                <span>{MATCH_TYPE_LABEL[matchType]}</span>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="condition">{MATCH_TYPE_LABEL.condition}</SelectItem>
                <SelectItem value="keyword">{MATCH_TYPE_LABEL.keyword}</SelectItem>
                <SelectItem value="regex">{MATCH_TYPE_LABEL.regex}</SelectItem>
                <SelectItem value="llm_intent">{MATCH_TYPE_LABEL.llm_intent}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Match config — per-type editor */}
          {matchType === "condition" && (
            <ConditionEditor
              value={matchConfig}
              onChange={setMatchConfig}
              trustedPaths={trustedPaths}
            />
          )}
          {matchType === "keyword" && (
            <KeywordEditor value={matchConfig} onChange={setMatchConfig} />
          )}
          {matchType === "regex" && (
            <RegexEditor value={matchConfig} onChange={setMatchConfig} />
          )}
          {matchType === "llm_intent" && (
            <LLMIntentEditor
              value={matchConfig}
              onChange={setMatchConfig}
              categories={classifierCategories}
            />
          )}

          {/* Handler — Workflow only (Plan 31 scope) */}
          <div className="pt-2">
            <Label className="text-xs">派发到 Workflow</Label>
            <WorkflowHandlerEditor
              agentId={agent.id}
              handlerId={handlerId}
              handlerConfig={handlerConfig}
              onChange={(hid, hcfg) => {
                setHandlerId(hid)
                setHandlerConfig(hcfg)
              }}
            />
          </div>

          {/* On-error policy */}
          <div className="flex flex-col gap-2">
            <Label className="text-xs">handler 失败时</Label>
            <Select value={onError} onValueChange={(v) => v && setOnError(v as OnHandlerError)}>
              <SelectTrigger>
                <span>{ON_ERROR_LABEL[onError]}</span>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="use_default">{ON_ERROR_LABEL.use_default}</SelectItem>
                <SelectItem value="fallback_next">{ON_ERROR_LABEL.fallback_next}</SelectItem>
                <SelectItem value="return_error">{ON_ERROR_LABEL.return_error}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <input
              id="rule-active"
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />
            <Label htmlFor="rule-active" className="text-xs">激活（停用后此规则不参与评估）</Label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {saving ? "保存中..." : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function _isValid(mt: MatchType, mc: Record<string, unknown>, hid: string | null) {
  if (mt === "keyword") {
    const l = (mc.any_of as string[]) ?? []
    if (l.length === 0) return false
  }
  if (mt === "regex") {
    if (!mc.pattern || typeof mc.pattern !== "string") return false
  }
  if (mt === "condition") {
    if (!mc.path || !mc.op) return false
  }
  if (mt === "llm_intent") {
    if (!mc.category) return false
  }
  if (!hid) return false
  return true
}
