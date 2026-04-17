import { useNavigate } from "react-router-dom"
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { Agent, AgentType } from "@/api/agent"

const typeLabel: Record<AgentType, string> = {
  simple: "简易智能体",
  workflow: "工作流",
  orchestrator: "编排",
}

interface AgentCardProps {
  agent: Agent
  onDelete: (agent: Agent) => void
}

export function AgentCard({ agent, onDelete }: AgentCardProps) {
  const navigate = useNavigate()
  const kbCount = agent.knowledge_base_ids?.length ?? 0

  return (
    <Card
      className="group cursor-pointer transition-shadow hover:shadow-elevation-2"
      onClick={() => navigate(`/agents/${agent.id}`)}
    >
      <CardHeader>
        <div className="flex items-start gap-3">
          <Avatar className="h-9 w-9 shrink-0">
            <AvatarFallback className="text-sm font-medium">
              {agent.name.charAt(0).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <CardTitle className="truncate">{agent.name}</CardTitle>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  className="inline-flex size-7 shrink-0 items-center justify-center rounded opacity-0 transition-opacity hover:bg-accent group-hover:opacity-100 data-[state=open]:opacity-100"
                  title="操作"
                  onClick={(e) => e.stopPropagation()}
                />
              }
            >
              <MoreHorizontal className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="text-sm" onClick={(e) => e.stopPropagation()}>
              <DropdownMenuItem
                onClick={(e) => { e.stopPropagation(); navigate(`/agents/${agent.id}`) }}
              >
                <Pencil className="mr-2 size-3.5" /> 配置
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={(e) => { e.stopPropagation(); onDelete(agent) }}
                className="text-destructive"
              >
                <Trash2 className="mr-2 size-3.5" /> 删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        {agent.description && (
          <CardDescription className="line-clamp-2">{agent.description}</CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary">{typeLabel[agent.agent_type]}</Badge>
          {kbCount > 0 && <span>{kbCount} 知识库</span>}
          {agent.model_name && (
            <Badge variant="outline">{agent.model_name}</Badge>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
