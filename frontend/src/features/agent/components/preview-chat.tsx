import { useEffect } from "react"
import { Bot, RotateCcw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { ChatWindow } from "@/features/chat/components/chat-window"
import { useChatStore } from "@/stores/chat"
import type { Agent } from "@/api/agent"

interface PreviewChatProps {
  agent: Agent
}

/**
 * Simplified chat pane for the Agent Workbench. No conversation list, no
 * persistent session — conversation_id starts null; the SSE pipeline creates
 * one on first send. "开新对话" resets local state (does not delete from DB).
 */
export function PreviewChat({ agent }: PreviewChatProps) {
  const reset = useChatStore((s) => s.reset)
  const activeConversationId = useChatStore((s) => s.activeConversationId)

  // Start fresh whenever the agent itself changes.
  useEffect(() => {
    reset()
  }, [agent.id, reset])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-12 items-center justify-between border-b px-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Bot className="size-4" />
          </div>
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-medium">{agent.name}</span>
            <span className="text-[10px] text-muted-foreground">预览模式 · 不保存历史</span>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={reset}
          title="清空当前预览对话"
          className="h-7 px-2"
        >
          <RotateCcw className="mr-1 size-3.5" /> 开新对话
        </Button>
      </div>
      <div className="flex-1 min-h-0">
        <ChatWindow
          agentId={agent.id}
          conversationId={activeConversationId}
          welcomeMessage={agent.welcome_message ?? undefined}
        />
      </div>
    </div>
  )
}
