import { useState } from "react"
import { useSearchParams } from "react-router-dom"

import type { Agent } from "@/api/agent"
import { WorkflowEditor } from "@/features/workflow/editor"

import {
  AgentMenu,
  defaultMenuFor,
  findMenuItem,
  menuGroupsForAgent,
} from "./agent-menu"
import { PreviewChat } from "./preview-chat"
import { PersonaPanel } from "./panels/persona-panel"
import { KnowledgePanel } from "./panels/knowledge-panel"
import { ChannelsPanel } from "./panels/channels-panel"
import { PlaceholderPanel } from "./panels/placeholder-panel"
import { RulesPanel } from "./panels/rules-panel"
import { ClassifierPanel } from "./panels/classifier-panel"
import { TracesPanel } from "./panels/traces-panel"
import { WorkflowsPanel } from "./panels/workflows-panel"
import { WorkflowAgentWorkbench } from "./workflow-agent-workbench"

interface AgentWorkbenchProps {
  agent: Agent
  onUpdated: () => void
  onDeleted?: () => void
}


/**
 * Agent Workbench — adapts to agent_type.
 *
 * Simple agents: persona / knowledge / channels / capabilities.
 * Workflow agents: workflow / channels / capabilities. persona + knowledge
 * are subsumed by the workflow itself (spec 12 §Phase 1b).
 *
 * Both keep Channels so spec 22 §5 "four modes available for both Simple
 * Agent and Workflow Agent" actually holds in the UI.
 */
export function AgentWorkbench({ agent, onUpdated, onDeleted }: AgentWorkbenchProps) {
  // Workflow agents get a dedicated two-column layout — workflow IS the
  // configuration, so there's no preview chat / persona panel.
  if ((agent.agent_type ?? "simple") === "workflow") {
    return <WorkflowAgentWorkbench agent={agent} />
  }

  const [searchParams, setSearchParams] = useSearchParams()
  const agentType = agent.agent_type ?? "simple"
  const defaultMenu = defaultMenuFor(agentType)
  const requested = searchParams.get("menu") || defaultMenu

  // Guard against menu ids that don't belong to this agent type (e.g. user
  // switched agent_type after bookmarking a URL).
  const groups = menuGroupsForAgent(agentType)
  const valid = groups.some((g) => g.items.some((i) => i.id === requested))
  const activeMenu = valid ? requested : defaultMenu
  const [menuCollapsed, setMenuCollapsed] = useState(false)

  // Plan 31 N2.14 — Workflow editor needs lots of canvas; ?fullscreen=1
  // hides the left PreviewChat + AgentMenu and gives the active panel
  // the whole screen. Currently only Orchestrator Workflows panel opts in.
  const isFullscreen = searchParams.get("fullscreen") === "1"
  function toggleFullscreen() {
    const next = new URLSearchParams(searchParams)
    if (isFullscreen) next.delete("fullscreen")
    else next.set("fullscreen", "1")
    setSearchParams(next, { replace: true })
  }

  function selectMenu(id: string) {
    const next = new URLSearchParams(searchParams)
    next.set("menu", id)
    setSearchParams(next, { replace: true })
  }

  function renderPanel() {
    switch (activeMenu) {
      case "persona":
        return <PersonaPanel agent={agent} onUpdated={onUpdated} onDeleted={onDeleted} />
      case "knowledge":
        return <KnowledgePanel agent={agent} onUpdated={onUpdated} />
      case "workflow":
        if (!agent.workflow_id) {
          return (
            <div className="p-6 text-sm text-muted-foreground">
              工作流智能体缺少绑定的工作流。此状态通常由历史数据迁移造成；
              请删除该智能体后重新创建。
            </div>
          )
        }
        return (
          <div className="h-full">
            <WorkflowEditor workflowId={agent.workflow_id} embedded />
          </div>
        )
      case "channels":
        return <ChannelsPanel agent={agent} />
      case "rules":
        return <RulesPanel agent={agent} onUpdated={onUpdated} />
      case "classifier":
        return <ClassifierPanel agent={agent} onUpdated={onUpdated} />
      case "traces":
        return <TracesPanel agent={agent} />
      case "workflows":
        return (
          <WorkflowsPanel
            agent={agent}
            onUpdated={onUpdated}
            fullscreen={isFullscreen}
            onToggleFullscreen={toggleFullscreen}
          />
        )
      default: {
        const item = findMenuItem(activeMenu)
        if (item && item.phase) return <PlaceholderPanel item={item} />
        return <PlaceholderPanel item={findMenuItem(defaultMenu)!} />
      }
    }
  }

  // Fullscreen mode — hide PreviewChat + AgentMenu, render active panel only.
  // Only supported by panels that expose their own "exit fullscreen" control.
  if (isFullscreen && activeMenu === "workflows") {
    return (
      <div className="flex h-full min-h-0 flex-1 overflow-hidden rounded-lg border bg-card">
        {renderPanel()}
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-1 gap-3">
      <div className="h-full w-[450px] shrink-0 overflow-hidden rounded-lg border bg-card">
        <PreviewChat agent={agent} />
      </div>

      <div className="flex h-full min-w-0 flex-1 overflow-hidden rounded-lg border bg-card">
        <AgentMenu
          activeMenu={activeMenu}
          onSelect={selectMenu}
          collapsed={menuCollapsed}
          onToggleCollapse={() => setMenuCollapsed((v) => !v)}
          agentType={agentType}
        />
        <div className="min-w-0 flex-1">{renderPanel()}</div>
      </div>
    </div>
  )
}
