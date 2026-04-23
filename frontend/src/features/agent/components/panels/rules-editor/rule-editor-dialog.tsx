/**
 * 规则新建/编辑对话框。
 *
 * 核心产品约束：condition 一定是 form-based（path 下拉 + op 下拉 +
 * value 输入）——运营用户不写 JSONLogic 文本。keyword / regex 同理给
 * 专用编辑器；llm_intent 的 category 是从 Agent classifier 定义的类别
 * 里下拉，不能自由输入。
 */
import { useEffect, useMemo, useState } from "react"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

import type { Agent } from "@/api/agent"
import type {
  AgentRule, CreateRulePayload, HandlerType, MatchType, OnHandlerError,
} from "@/api/orchestrator"

import { ConditionEditor } from "./condition-editor"
import { KeywordEditor } from "./keyword-editor"
import { RegexEditor } from "./regex-editor"
import { LLMIntentEditor } from "./llm-intent-editor"
import { HandlerEditor } from "./handler-editor"

interface Props {
  open: boolean
  onOpenChange: (v: boolean) => void
  editingRule: AgentRule | null
  agent: Agent
  onSave: (payload: CreateRulePayload) => Promise<void>
}


export function RuleEditorDialog({ open, onOpenChange, editingRule, agent, onSave }: Props) {
  const isEdit = editingRule !== null

  const [matchType, setMatchType] = useState<MatchType>("keyword")
  const [matchConfig, setMatchConfig] = useState<Record<string, unknown>>({})
  const [handlerType, setHandlerType] = useState<HandlerType>("simple_agent")
  const [handlerId, setHandlerId] = useState<string | null>(null)
  const [handlerConfig, setHandlerConfig] = useState<Record<string, unknown>>({})
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
      setHandlerType(editingRule.handler_type)
      setHandlerId(editingRule.handler_id)
      setHandlerConfig(editingRule.handler_config)
      setOnError(editingRule.on_handler_error)
      setActive(editingRule.is_active)
    } else {
      setMatchType("keyword")
      setMatchConfig({ any_of: [], case_sensitive: false })
      setHandlerType("simple_agent")
      setHandlerId(null)
      setHandlerConfig({})
      setOnError("use_default")
      setActive(true)
    }
  }, [open, editingRule])

  function handleMatchTypeChange(v: MatchType) {
    setMatchType(v)
    // Seed match_config with per-type default so editors don't crash on undefined
    if (v === "keyword") setMatchConfig({ any_of: [], case_sensitive: false })
    else if (v === "regex") setMatchConfig({ pattern: "", flags: "" })
    else if (v === "condition") setMatchConfig({ path: trustedPaths[0] ?? "", op: "==", value: "" })
    else if (v === "llm_intent") setMatchConfig({ category: classifierCategories[0]?.name ?? "" })
  }

  function handleHandlerTypeChange(v: HandlerType) {
    setHandlerType(v)
    setHandlerId(null)
    // Per-handler default config
    if (v === "workflow") setHandlerConfig({ input_mapping: { query: "$message" } })
    else if (v === "mcp_tool") setHandlerConfig({ tool_name: "", arg_template: { input: "$message" } })
    else setHandlerConfig({})
  }

  async function handleSubmit() {
    setSaving(true)
    try {
      await onSave({
        match_type: matchType,
        match_config: matchConfig,
        handler_type: handlerType,
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

  const canSubmit = !saving && _isValid(matchType, matchConfig, handlerType, handlerId)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑规则" : "新建规则"}</DialogTitle>
          <DialogDescription>
            匹配条件 → 派发 handler；运行时按优先级评估
          </DialogDescription>
        </DialogHeader>

        <div className="flex max-h-[65vh] flex-col gap-4 overflow-y-auto pr-1">
          {/* Match type */}
          <div className="flex flex-col gap-2">
            <Label className="text-xs">匹配类型</Label>
            <Select value={matchType} onValueChange={(v) => v && handleMatchTypeChange(v as MatchType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="condition">条件（metadata 表达式）</SelectItem>
                <SelectItem value="keyword">关键词</SelectItem>
                <SelectItem value="regex">正则</SelectItem>
                <SelectItem value="llm_intent">LLM 意图分类</SelectItem>
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

          {/* Handler */}
          <div className="pt-2">
            <Label className="text-xs">派发到</Label>
            <Select value={handlerType} onValueChange={(v) => v && handleHandlerTypeChange(v as HandlerType)}>
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="simple_agent">Simple Agent</SelectItem>
                <SelectItem value="workflow">Workflow</SelectItem>
                <SelectItem value="mcp_tool">MCP 工具</SelectItem>
                <SelectItem value="sub_agent">Sub Agent（递归）</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <HandlerEditor
            handlerType={handlerType}
            handlerId={handlerId}
            handlerConfig={handlerConfig}
            onChange={(hid, hcfg) => {
              setHandlerId(hid)
              setHandlerConfig(hcfg)
            }}
          />

          {/* On-error policy */}
          <div className="flex flex-col gap-2">
            <Label className="text-xs">handler 失败时</Label>
            <Select value={onError} onValueChange={(v) => v && setOnError(v as OnHandlerError)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="use_default">走默认 handler（推荐）</SelectItem>
                <SelectItem value="fallback_next">继续尝试下一条规则</SelectItem>
                <SelectItem value="return_error">直接返回错误给用户</SelectItem>
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


function _isValid(mt: MatchType, mc: Record<string, unknown>, ht: HandlerType, hid: string | null) {
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
  // All supported handler_types require handler_id
  if (!hid) return false
  if (ht === "mcp_tool" && !(mc && "tool_name" in mc)) {
    // handler_config.tool_name check is done inside HandlerEditor state
  }
  return true
}
