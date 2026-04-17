import { useCallback, useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"

import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { BreadcrumbNav } from "@/components/layout/breadcrumb-nav"
import { AgentWorkbench } from "@/features/agent/components/agent-workbench"
import { agentApi, type Agent } from "@/api/agent"
import { useAgentStore } from "@/stores/agent"
import { useChatStore } from "@/stores/chat"

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const setCurrentAgent = useAgentStore((s) => s.setCurrentAgent)
  const resetChat = useChatStore((s) => s.reset)
  const [agent, setAgent] = useState<Agent | null>(null)
  const [initLoading, setInitLoading] = useState(true)

  // Silent reload — update state without triggering the full-page spinner.
  // Used by child panels after save so they don't get unmounted mid-stream.
  const reload = useCallback(async () => {
    if (!id) return
    const data = await agentApi.get(id)
    setAgent(data)
  }, [id])

  // Initial fetch on id change — only time the spinner shows.
  useEffect(() => {
    if (!id) return
    let cancelled = false
    setInitLoading(true)
    setCurrentAgent(id)
    agentApi.get(id)
      .then((data) => { if (!cancelled) setAgent(data) })
      .finally(() => { if (!cancelled) setInitLoading(false) })
    return () => {
      cancelled = true
      resetChat()
    }
  }, [id, setCurrentAgent, resetChat])

  if (initLoading || !agent) {
    return <LoadingSpinner className="py-32" size="lg" />
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <BreadcrumbNav />
      <h1 className="mb-3 text-xl font-semibold">{agent.name}</h1>
      <div className="flex min-h-0 flex-1">
        <AgentWorkbench
          agent={agent}
          onUpdated={reload}
          onDeleted={() => navigate("/agents", { replace: true })}
        />
      </div>
    </div>
  )
}
