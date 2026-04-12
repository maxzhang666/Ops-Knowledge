import { useNavigate } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import type { Agent, AgentType } from "@/api/agent"

const typeLabel: Record<AgentType, string> = {
  simple: "Simple",
  rag: "RAG",
  workflow: "Workflow",
}

interface AgentCardProps {
  agent: Agent
}

export function AgentCard({ agent }: AgentCardProps) {
  const navigate = useNavigate()

  return (
    <Card
      className="cursor-pointer transition-shadow hover:shadow-md"
      onClick={() => navigate(`/agents/${agent.id}`)}
    >
      <CardHeader>
        <div className="flex items-center gap-3">
          <Avatar className="h-9 w-9 shrink-0">
            <AvatarFallback className="text-sm font-medium">
              {agent.name.charAt(0).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <CardTitle className="truncate">{agent.name}</CardTitle>
          </div>
        </div>
        {agent.description && (
          <CardDescription className="line-clamp-2">{agent.description}</CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary">{typeLabel[agent.agent_type]}</Badge>
          {agent.knowledge_base_ids.length > 0 && (
            <span>{agent.knowledge_base_ids.length} 知识库</span>
          )}
          {agent.model_name && (
            <Badge variant="outline">{agent.model_name}</Badge>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
