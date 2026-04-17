import { useMemo } from "react"
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Database,
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
    ],
  },
  {
    id: "capabilities",
    label: "能力扩展",
    items: [
      { id: "tools", label: "内置工具", icon: Wrench, phase: "2", description: "knowledge_search / code_execute / http_request 等系统内置工具" },
      { id: "mcp", label: "MCP", icon: Zap, phase: "2", description: "MCP Server 绑定，扩展第三方能力" },
      { id: "skill", label: "Skill", icon: Sparkles, phase: "3", description: "技能包（Instructions + Tools + Templates）" },
    ],
  },
  {
    id: "publish",
    label: "发布运营",
    items: [
      { id: "channels", label: "渠道", icon: Radio, phase: "1b", description: "Webhook / Embed 组件 / API Key" },
      { id: "stats", label: "统计", icon: BarChart3, phase: "2", description: "对话量、反馈率、使用趋势" },
    ],
  },
]

export const DEFAULT_MENU = "persona"

interface AgentMenuProps {
  activeMenu: string
  onSelect: (menu: string) => void
  collapsed: boolean
  onToggleCollapse: () => void
}

export function AgentMenu({
  activeMenu, onSelect, collapsed, onToggleCollapse,
}: AgentMenuProps) {
  const groups = useMemo(() => AGENT_MENU_GROUPS, [])

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
