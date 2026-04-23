import { useMemo } from "react"
import {
  BarChart3,
  Brain,
  ChevronLeft,
  ChevronRight,
  Database,
  FileCode2,
  GitBranch,
  History,
  ListOrdered,
  Radio,
  Sparkles,
  User,
  Wrench,
  Zap,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

/**
 * Menu item definition. `phase` marks items that are not yet implemented;
 * clicking still switches to the menu but the right pane renders
 * `<PlaceholderPanel>` instead of a form.
 */
export interface MenuItem {
  id: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  phase?: "1b" | "2" | "3"
  description?: string
}

interface MenuGroup {
  id: string
  label: string
  items: MenuItem[]
}

export const AGENT_MENU_GROUPS: MenuGroup[] = [
  {
    id: "basic",
    label: "基础配置",
    items: [
      { id: "persona", label: "人设", icon: User, description: "角色身份、模型、欢迎语、思维链" },
      { id: "knowledge", label: "知识库", icon: Database, description: "KB 关联与检索配置" },
      { id: "workflow", label: "工作流", icon: GitBranch, description: "可视化编辑工作流（仅工作流智能体）" },
    ],
  },
  {
    // Plan 31 — Orchestrator 的 SOP 库：本 Agent 名下 Workflow 列表
    // + 新建 + 内嵌编辑器。workflows.owner_agent_id == this_agent.id。
    id: "sop",
    label: "SOP 流程",
    items: [
      { id: "workflows", label: "工作流列表", icon: FileCode2, description: "本编排智能体名下的 SOP；新建 / 编辑 / 删除" },
    ],
  },
  {
    // Plan 31 — Orchestrator Agent 专属的路由配置组。
    // menuGroupsForAgent 里对非 orchestrator 类型会整组裁掉。
    id: "routing",
    label: "路由配置",
    items: [
      { id: "rules", label: "规则表", icon: ListOrdered, description: "条件 / 关键词 / 正则 / LLM 意图 → 派发到哪个 SOP" },
      { id: "classifier", label: "意图分类器", icon: Brain, description: "LLM 分类器模型 + 类别 + 阈值配置" },
      { id: "traces", label: "路由审计", icon: History, description: "最近路由决策 + 命中统计" },
    ],
  },
  {
    id: "capabilities",
    label: "能力扩展",
    items: [
      // Simple Agent 不直接支持工具/MCP（runtime 仍是 P1a chat pipeline）；
      // 要使用请创建 Workflow Agent，在 Workflow 编辑器的 "Agent (ReAct)"
      // 节点里配置 builtin_tools / mcp_server_ids。Simple Agent 的 tools 接入
      // 留到 P3 随 LangGraph 收敛（spec 04 §Agent Runtime）。
      { id: "tools", label: "内置工具", icon: Wrench, phase: "3", description: "knowledge_search / code_execute / http_request —— Simple Agent 暂不支持，请创建 Workflow Agent，在其 Agent 节点配置" },
      { id: "mcp", label: "MCP", icon: Zap, phase: "3", description: "MCP Server 绑定 —— Simple Agent 暂不支持，请创建 Workflow Agent，在其 Agent 节点配置" },
      { id: "skill", label: "Skill", icon: Sparkles, phase: "3", description: "技能包（Instructions + Tools + Templates）" },
    ],
  },
  {
    id: "publish",
    label: "发布运营",
    items: [
      { id: "channels", label: "渠道", icon: Radio, description: "API 调用（4 模式）+ API Key 快捷入口；Embed / Outbound Webhook 见 Phase 2" },
      { id: "stats", label: "统计", icon: BarChart3, phase: "2", description: "对话量、反馈率、使用趋势" },
    ],
  },
]

export const DEFAULT_MENU = "persona"


/**
 * Filter menu items by agent_type.
 *  - Simple agent: 基础（persona/knowledge）+ capabilities(placeholder) + publish
 *  - Workflow agent: 基础（workflow only）+ capabilities(placeholder) + publish
 *    （注意：Workflow Agent 自有 WorkflowAgentWorkbench，一般不走此菜单）
 *  - Orchestrator agent: 基础（persona 保留作身份配置）+ **routing 组** + publish
 *    路由组的 rules/classifier/traces 是 Plan 31 N1 后端真实接入点；
 *    capabilities 组对 orchestrator 没意义（通过规则派发到其他 agent）→ 隐藏
 */
export function menuGroupsForAgent(agentType: string): MenuGroup[] {
  return AGENT_MENU_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((item) => {
      if (agentType === "workflow") {
        // Workflow Agent 自有 WorkflowAgentWorkbench，一般不走此菜单
        if (g.id === "routing" || g.id === "sop") return false
        return item.id !== "persona" && item.id !== "knowledge"
      }
      if (agentType === "orchestrator") {
        // Orchestrator 有自己的 SOP 库 + 路由组；基础组仅保留 persona（头像/欢迎语）
        if (g.id === "capabilities") return false
        if (g.id === "basic") return item.id === "persona"
        return item.id !== "workflow" && item.id !== "knowledge"
      }
      // simple agent
      if (g.id === "routing" || g.id === "sop") return false
      return item.id !== "workflow"
    }),
  })).filter((g) => g.items.length > 0)
}


export function defaultMenuFor(agentType: string): string {
  if (agentType === "workflow") return "workflow"
  // Orchestrator 默认打开 "SOP 流程" —— 用户最常做的第一件事是编辑 SOP
  if (agentType === "orchestrator") return "workflows"
  return DEFAULT_MENU
}

interface AgentMenuProps {
  activeMenu: string
  onSelect: (menu: string) => void
  collapsed: boolean
  onToggleCollapse: () => void
  agentType?: string
}

export function AgentMenu({
  activeMenu, onSelect, collapsed, onToggleCollapse, agentType = "simple",
}: AgentMenuProps) {
  const groups = useMemo(() => menuGroupsForAgent(agentType), [agentType])

  return (
    <div
      className={cn(
        "flex h-full flex-col border-r bg-background transition-[width] duration-200",
        collapsed ? "w-14" : "w-56",
      )}
    >
      <div className="flex h-10 items-center justify-end border-b px-2">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="inline-flex size-7 items-center justify-center rounded-md hover:bg-accent"
          title={collapsed ? "展开菜单" : "收起菜单"}
        >
          {collapsed ? <ChevronRight className="size-4" /> : <ChevronLeft className="size-4" />}
        </button>
      </div>

      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-2">
        {groups.map((group) => (
          <div key={group.id} className="flex flex-col">
            {!collapsed ? (
              <div className="mt-2 mb-1 px-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {group.label}
              </div>
            ) : (
              <div className="my-1 h-px bg-border" />
            )}
            {group.items.map((item) => {
              const Icon = item.icon
              const active = activeMenu === item.id
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelect(item.id)}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-foreground/80 hover:bg-accent hover:text-foreground",
                    collapsed && "justify-center",
                  )}
                >
                  <Icon className={cn("size-4 shrink-0", active && "text-primary")} />
                  {!collapsed && (
                    <span className="flex-1 truncate text-left">{item.label}</span>
                  )}
                  {!collapsed && item.phase && (
                    <Badge variant="outline" className="h-4 px-1 text-[9px] font-normal">
                      {item.phase === "1b" ? "P1b" : `P${item.phase}`}
                    </Badge>
                  )}
                </button>
              )
            })}
          </div>
        ))}
      </nav>
    </div>
  )
}

export function findMenuItem(id: string): MenuItem | undefined {
  for (const g of AGENT_MENU_GROUPS) {
    const found = g.items.find((i) => i.id === id)
    if (found) return found
  }
  return undefined
}
