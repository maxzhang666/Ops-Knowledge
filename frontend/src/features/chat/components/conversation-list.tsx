import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2, MessageCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { chatApi, type Conversation } from "@/api/chat"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { TimeDisplay } from "@/components/shared/time-display"

interface ConversationListProps {
  agentId: string
  activeId: string | null
  onSelect: (id: string) => void
  onCreated: (id: string) => void
}

export function ConversationList({ agentId, activeId, onSelect, onCreated }: ConversationListProps) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const load = useCallback(async () => {
    const res = await chatApi.listConversations(agentId)
    setConversations(res.items)
  }, [agentId])

  useEffect(() => {
    load()
  }, [load])

  async function handleCreate() {
    const conv = await chatApi.createConversation(agentId)
    setConversations((prev) => [conv, ...prev])
    onCreated(conv.id)
  }

  async function handleDelete() {
    if (!deleteTarget) return
    await chatApi.deleteConversation(deleteTarget)
    setConversations((prev) => prev.filter((c) => c.id !== deleteTarget))
    if (activeId === deleteTarget) onSelect("")
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-sm font-medium">对话列表</span>
        <Button variant="ghost" size="icon" onClick={handleCreate}>
          <Plus className="size-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-0.5 p-2">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={cn(
                "group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                activeId === conv.id && "bg-accent",
              )}
              onClick={() => onSelect(conv.id)}
            >
              <MessageCircle className="size-3.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate">{conv.title || "新对话"}</p>
                <p className="text-xs text-muted-foreground">
                  <TimeDisplay value={conv.updated_at} />
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="size-6 opacity-0 group-hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation()
                  setDeleteTarget(conv.id)
                }}
              >
                <Trash2 className="size-3" />
              </Button>
            </div>
          ))}
        </div>
      </ScrollArea>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除对话"
        description="确认删除此对话及所有消息？此操作不可撤销。"
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}
