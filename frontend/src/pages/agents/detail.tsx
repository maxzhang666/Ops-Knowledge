import { useCallback, useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { BreadcrumbNav } from "@/components/layout/breadcrumb-nav"
import { AgentConfigForm } from "@/features/agent/components/agent-config-form"
import { ConversationList } from "@/features/chat/components/conversation-list"
import { ChatWindow } from "@/features/chat/components/chat-window"
import { agentApi, type Agent } from "@/api/agent"
import { useAgentStore } from "@/stores/agent"
import { useChatStore } from "@/stores/chat"

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const setCurrentAgent = useAgentStore((s) => s.setCurrentAgent)
  const activeConversationId = useChatStore((s) => s.activeConversationId)
  const setActiveConversation = useChatStore((s) => s.setActiveConversation)
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
    return () => {
      setActiveConversation(null)
    }
  }, [load, setActiveConversation])

  if (loading || !agent) {
    return <LoadingSpinner className="py-32" size="lg" />
  }

  return (
    <div className="flex h-full flex-col">
      <BreadcrumbNav />
      <h1 className="mb-4 text-xl font-semibold">{agent.name}</h1>

      <Tabs defaultValue="conversations" className="flex min-h-0 flex-1 flex-col">
        <TabsList>
          <TabsTrigger value="conversations">对话</TabsTrigger>
          <TabsTrigger value="config">配置</TabsTrigger>
        </TabsList>

        <TabsContent value="conversations" className="min-h-0 flex-1">
          <div className="mt-4 flex h-[calc(100vh-280px)] gap-0 overflow-hidden rounded-lg border">
            <aside className="w-56 shrink-0 border-r">
              <ConversationList
                agentId={agent.id}
                activeId={activeConversationId}
                onSelect={setActiveConversation}
                onCreated={setActiveConversation}
              />
            </aside>
            <div className="min-w-0 flex-1">
              <ChatWindow
                agentId={agent.id}
                conversationId={activeConversationId}
                welcomeMessage={agent.welcome_message}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="config">
          <AgentConfigForm agent={agent} onUpdated={load} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
