import { useCallback, useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { BreadcrumbNav } from "@/components/layout/breadcrumb-nav"
import { AgentConfigForm } from "@/features/agent/components/agent-config-form"
import { agentApi, type Agent } from "@/api/agent"
import { useAgentStore } from "@/stores/agent"

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const setCurrentAgent = useAgentStore((s) => s.setCurrentAgent)
  const [agent, setAgent] = useState<Agent | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const data = await agentApi.get(id)
      setAgent(data)
      setCurrentAgent(id)
    } finally {
      setLoading(false)
    }
  }, [id, setCurrentAgent])

  useEffect(() => {
    load()
  }, [load])

  if (loading || !agent) {
    return <LoadingSpinner className="py-32" size="lg" />
  }

  return (
    <div>
      <BreadcrumbNav />
      <h1 className="mb-4 text-xl font-semibold">{agent.name}</h1>

      <Tabs defaultValue="conversations">
        <TabsList>
          <TabsTrigger value="conversations">对话</TabsTrigger>
          <TabsTrigger value="config">配置</TabsTrigger>
        </TabsList>

        <TabsContent value="conversations">
          <div className="mt-4 text-sm text-muted-foreground">对话功能将在下一步实现</div>
        </TabsContent>

        <TabsContent value="config">
          <AgentConfigForm agent={agent} onUpdated={load} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
