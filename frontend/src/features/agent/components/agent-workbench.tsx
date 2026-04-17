import { useState } from "react"
import { useSearchParams } from "react-router-dom"

import type { Agent } from "@/api/agent"

import { AgentMenu, DEFAULT_MENU, findMenuItem } from "./agent-menu"
import { PreviewChat } from "./preview-chat"
import { PersonaPanel } from "./panels/persona-panel"
import { KnowledgePanel } from "./panels/knowledge-panel"
import { PlaceholderPanel } from "./panels/placeholder-panel"

interface AgentWorkbenchProps {
  agent: Agent
  onUpdated: () => void
  onDeleted?: () => void
}

export function AgentWorkbench({ agent, onUpdated, onDeleted }: AgentWorkbenchProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeMenu = searchParams.get("menu") || DEFAULT_MENU
  const [menuCollapsed, setMenuCollapsed] = useState(false)

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
      default: {
        const item = findMenuItem(activeMenu)
        if (item && item.phase) return <PlaceholderPanel item={item} />
        return <PlaceholderPanel item={findMenuItem(DEFAULT_MENU)!} />
      }
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-1 gap-3">
      {/* Left Card — fixed 450px preview chat */}
      <div className="h-full w-[450px] shrink-0 overflow-hidden rounded-lg border bg-card">
        <PreviewChat agent={agent} />
      </div>

      {/* Right Card — fills remaining width: menu + panel */}
      <div className="flex h-full min-w-0 flex-1 overflow-hidden rounded-lg border bg-card">
        <AgentMenu
          activeMenu={activeMenu}
          onSelect={selectMenu}
          collapsed={menuCollapsed}
          onToggleCollapse={() => setMenuCollapsed((v) => !v)}
        />
        <div className="min-w-0 flex-1">{renderPanel()}</div>
      </div>
    </div>
  )
}
