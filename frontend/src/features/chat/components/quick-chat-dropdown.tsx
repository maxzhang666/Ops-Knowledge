import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { MessageSquare, Bot } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { agentApi, type Agent } from "@/api/agent"

export function QuickChatDropdown() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])

  const load = useCallback(async () => {
    try {
      const res = await agentApi.list({ page_size: "10" })
      setAgents(res.items)
    } catch { /* silent */ }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" title="快速对话" />}>
        <MessageSquare className="h-4 w-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>选择智能体</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {agents.length === 0 ? (
          <DropdownMenuItem disabled>暂无智能体</DropdownMenuItem>
        ) : (
          agents.map((agent) => (
            <DropdownMenuItem
              key={agent.id}
              onClick={() => navigate(`/agents/${agent.id}`)}
            >
              <Bot className="mr-2 h-4 w-4" />
              {agent.name}
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
