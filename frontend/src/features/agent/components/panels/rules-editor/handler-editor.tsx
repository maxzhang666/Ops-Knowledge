/**
 * 按 handler_type 渲染 handler_id picker + 必要的 handler_config 字段。
 *
 * simple_agent / sub_agent: AgentPicker
 * workflow: WorkflowPicker + input_mapping 编辑器
 * mcp_tool: MCPServerPicker + tool_name 下拉 + arg_template 编辑
 */
import { useEffect, useState } from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { agentApi, type Agent } from "@/api/agent"
import { workflowApi, type WorkflowSummary } from "@/api/workflow"
import { mcpApi, type MCPServer, type MCPTool } from "@/api/mcp"
import type { HandlerType } from "@/api/orchestrator"

interface Props {
  handlerType: HandlerType
  handlerId: string | null
  handlerConfig: Record<string, unknown>
  onChange: (handlerId: string | null, handlerConfig: Record<string, unknown>) => void
}

export function HandlerEditor({ handlerType, handlerId, handlerConfig, onChange }: Props) {
  if (handlerType === "simple_agent" || handlerType === "sub_agent") {
    return (
      <AgentPicker
        value={handlerId}
        onChange={(v) => onChange(v, handlerConfig)}
        excludeSelf={handlerType === "sub_agent"}
        showOnlyTypes={handlerType === "simple_agent" ? ["simple"] : undefined}
      />
    )
  }
  if (handlerType === "workflow") {
    return (
      <WorkflowHandlerEditor
        handlerId={handlerId}
        handlerConfig={handlerConfig}
        onChange={onChange}
      />
    )
  }
  if (handlerType === "mcp_tool") {
    return (
      <MCPToolHandlerEditor
        handlerId={handlerId}
        handlerConfig={handlerConfig}
        onChange={onChange}
      />
    )
  }
  return null
}


function AgentPicker({
  value, onChange, showOnlyTypes,
}: {
  value: string | null
  onChange: (v: string | null) => void
  /** Orchestrator sub_agent: 理论上应排除当前 Agent 自身避免一级环；
   * 更深环由后端 DispatchContext.trace_lineage 检测。UI 层 N2 简化为
   * "允许选任意 Agent"，防环靠运行时。 */
  excludeSelf?: boolean
  showOnlyTypes?: string[]
}) {
  const [agents, setAgents] = useState<Agent[]>([])
  useEffect(() => {
    agentApi.list()
      .then((r) => {
        const items = Array.isArray(r) ? r : (r as { items?: Agent[] }).items ?? []
        setAgents(
          items.filter((a) => {
            if (showOnlyTypes && !showOnlyTypes.includes(a.agent_type ?? "simple")) return false
            return true
          }),
        )
      })
      .catch(() => setAgents([]))
  }, [showOnlyTypes?.join(",")])  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <Label className="text-[11px]">目标 Agent</Label>
      <Select value={value ?? ""} onValueChange={(v) => v && onChange(v)}>
        <SelectTrigger className="mt-1 h-8 text-xs">
          <SelectValue placeholder="选择 Agent" />
        </SelectTrigger>
        <SelectContent>
          {agents.map((a) => (
            <SelectItem key={a.id} value={a.id} className="text-xs">
              {a.name} <span className="ml-1 text-muted-foreground">({a.agent_type})</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}


function WorkflowHandlerEditor({
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

  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <Label className="text-[11px]">目标 Workflow</Label>
      <Select value={handlerId ?? ""} onValueChange={(v) => v && onChange(v, handlerConfig)}>
        <SelectTrigger className="mt-1 h-8 text-xs">
          <SelectValue placeholder="选择 Workflow" />
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
        <Label className="text-[11px]">输入映射（JSON；$message / $user.id / $metadata.input.x 可引用）</Label>
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
      </div>
    </div>
  )
}


function MCPToolHandlerEditor({
  handlerId, handlerConfig, onChange,
}: {
  handlerId: string | null
  handlerConfig: Record<string, unknown>
  onChange: (handlerId: string | null, handlerConfig: Record<string, unknown>) => void
}) {
  const [servers, setServers] = useState<MCPServer[]>([])
  const [tools, setTools] = useState<MCPTool[]>([])

  useEffect(() => {
    mcpApi.list(true).then(setServers).catch(() => setServers([]))
  }, [])

  useEffect(() => {
    if (!handlerId) { setTools([]); return }
    mcpApi.getTools(handlerId).then(setTools).catch(() => setTools([]))
  }, [handlerId])

  const toolName = (handlerConfig.tool_name as string) ?? ""
  const argTemplate = (handlerConfig.arg_template as Record<string, string>) ?? { input: "$message" }

  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <Label className="text-[11px]">MCP 服务器</Label>
      <Select value={handlerId ?? ""} onValueChange={(v) => v && onChange(v, handlerConfig)}>
        <SelectTrigger className="mt-1 h-8 text-xs">
          <SelectValue placeholder="选择 MCP Server" />
        </SelectTrigger>
        <SelectContent>
          {servers.map((s) => (
            <SelectItem key={s.id} value={s.id} className="text-xs">
              {s.name} <span className="ml-1 text-muted-foreground">({s.transport_type})</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {handlerId && (
        <>
          <div className="mt-3">
            <Label className="text-[11px]">工具</Label>
            <Select
              value={toolName}
              onValueChange={(v) => v && onChange(handlerId, { ...handlerConfig, tool_name: v })}
            >
              <SelectTrigger className="mt-1 h-8 text-xs">
                <SelectValue placeholder={tools.length ? "选择工具" : "该服务器无工具"} />
              </SelectTrigger>
              <SelectContent>
                {tools.map((t) => (
                  <SelectItem key={t.name} value={t.name} className="text-xs">
                    <span className="font-mono">{t.name}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="mt-3">
            <Label className="text-[11px]">参数模板（JSON）</Label>
            <Input
              className="mt-1 h-8 font-mono text-xs"
              value={JSON.stringify(argTemplate)}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value)
                  onChange(handlerId, { ...handlerConfig, arg_template: parsed })
                } catch {
                  /* keep typing */
                }
              }}
            />
          </div>
        </>
      )}
    </div>
  )
}
