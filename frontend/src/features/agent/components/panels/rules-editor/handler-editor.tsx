/**
 * Workflow handler editor (Plan 31 N2 — workflow-only scope).
 *
 * 只保留 Workflow；Simple Agent / MCP Tool / Sub Agent 在协议层保留
 * 但 UI 不暴露。一条规则命中 → 把 user message 按 input_mapping 填入
 * 变量后启动 Workflow 执行。
 */
import { useEffect, useState } from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { workflowApi, type WorkflowSummary } from "@/api/workflow"


export function WorkflowHandlerEditor({
  handlerId, handlerConfig, onChange,
}: {
  handlerId: string | null
  handlerConfig: Record<string, unknown>
  onChange: (handlerId: string | null, handlerConfig: Record<string, unknown>) => void
}) {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  useEffect(() => {
    workflowApi.list().then(setWorkflows).catch(() => setWorkflows([]))
  }, [])

  const mapping = (handlerConfig.input_mapping as Record<string, string>) ?? { query: "$message" }
  const selectedWorkflow = handlerId ? workflows.find((w) => w.id === handlerId) : undefined

  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <Label className="text-[11px]">目标 Workflow</Label>
      <Select value={handlerId ?? ""} onValueChange={(v) => v && onChange(v, handlerConfig)}>
        <SelectTrigger className="mt-1 h-8 text-xs">
          {/* memory:feedback_dropdown_display_label — 显示 name 不是 id */}
          {selectedWorkflow
            ? <span className="truncate">{selectedWorkflow.name}</span>
            : <SelectValue placeholder={workflows.length ? "选择 Workflow" : "暂无 Workflow，请先创建"} />}
        </SelectTrigger>
        <SelectContent>
          {workflows.map((w) => (
            <SelectItem key={w.id} value={w.id} className="text-xs">
              {w.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="mt-3">
        <Label className="text-[11px]">
          输入映射（JSON；<code>$message</code> / <code>$user.id</code> /
          <code>$metadata.input.x</code> 可引用）
        </Label>
        <Input
          className="mt-1 h-8 font-mono text-xs"
          value={JSON.stringify(mapping)}
          onChange={(e) => {
            try {
              const parsed = JSON.parse(e.target.value)
              onChange(handlerId, { ...handlerConfig, input_mapping: parsed })
            } catch {
              /* keep typing */
            }
          }}
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          默认把用户消息映射到 Workflow 的 <code>query</code> 变量。需要传其他字段（如部门 ID）
          可加 <code>{"{ \"dept_id\": \"$user.department_id\" }"}</code>。
        </p>
      </div>
    </div>
  )
}
