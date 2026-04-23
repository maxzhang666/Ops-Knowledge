import { useSearchParams } from "react-router-dom"
import { GitBranch, Radio } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Agent } from "@/api/agent"
import { WorkflowEditor } from "@/features/workflow/editor"
import { ChannelsPanel } from "./panels/channels-panel"


/**
 * Dedicated two-column layout for Workflow Agents — replaces the generic
 * Workbench (persona / knowledge / preview chat) which doesn't apply when
 * the workflow IS the agent configuration.
 *
 * Left: icon-label nav (流程 / 渠道 / 未来扩展项)
 * Right: the selected section's full canvas
 */

interface MenuItem {
  id: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  phase?: "2" | "3"
}

const MENU: MenuItem[] = [
  { id: "workflow", label: "流程", icon: GitBranch },
  { id: "channels", label: "渠道", icon: Radio },
]

const DEFAULT_MENU = "workflow"


export function WorkflowAgentWorkbench({ agent }: { agent: Agent }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const active = searchParams.get("menu") ?? DEFAULT_MENU
  const valid = MENU.some((m) => m.id === active)
  const menu = valid ? active : DEFAULT_MENU

  function select(id: string) {
    const next = new URLSearchParams(searchParams)
    next.set("menu", id)
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="flex h-full min-h-0 flex-1 gap-3">
      <aside className="h-full w-40 shrink-0 overflow-hidden rounded-lg border bg-card">
        <nav className="flex flex-col gap-1 p-2">
          {MENU.map((m) => {
            const Icon = m.icon
            const isActive = menu === m.id
            return (
              <button
                key={m.id}
                type="button"
                onClick={() => select(m.id)}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-foreground/80 hover:bg-accent",
                )}
              >
                <Icon className="size-4 shrink-0" />
                <span className="flex-1 text-left">{m.label}</span>
              </button>
            )
          })}
        </nav>
      </aside>

      <section className="flex min-w-0 flex-1 overflow-hidden rounded-lg border bg-card">
        {menu === "workflow" && agent.workflow_id ? (
          <WorkflowEditor workflowId={agent.workflow_id} embedded />
        ) : menu === "workflow" ? (
          <div className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
            工作流智能体缺少绑定的工作流，请删除重建。
          </div>
        ) : menu === "channels" ? (
          <ChannelsPanel agent={agent} />
        ) : null}
      </section>
    </div>
  )
}
