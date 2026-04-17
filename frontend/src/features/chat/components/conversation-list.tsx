import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Plus, MoreHorizontal, Pin, Pencil, Download, Trash2, MessageCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import { chatApi, type Conversation, type Message } from "@/api/chat"
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
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState("")
  const renameInputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    const res = await chatApi.listConversations(agentId)
    setConversations(res.items)
  }, [agentId])

  useEffect(() => {
    load()
  }, [load])

  // Focus rename input when entering edit mode
  useEffect(() => {
    if (editingId) {
      requestAnimationFrame(() => renameInputRef.current?.focus())
    }
  }, [editingId])

  const sorted = useMemo(() => {
    const pinned = conversations
      .filter((c) => c.is_pinned)
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    const unpinned = conversations
      .filter((c) => !c.is_pinned)
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    return [...pinned, ...unpinned]
  }, [conversations])

  async function handleCreate() {
    const conv = await chatApi.createConversation(agentId)
    setConversations((prev) => [conv, ...prev])
    onCreated(conv.id)
  }

  async function handleDelete() {
    if (!deleteTarget) return
    await chatApi.deleteConversation(agentId, deleteTarget)
    setConversations((prev) => prev.filter((c) => c.id !== deleteTarget))
    if (activeId === deleteTarget) onSelect("")
  }

  async function handleTogglePin(conv: Conversation) {
    const updated = await chatApi.updateConversation(agentId, conv.id, {
      is_pinned: !conv.is_pinned,
    })
    setConversations((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
  }

  function startRename(conv: Conversation) {
    setEditingId(conv.id)
    setEditTitle(conv.title || "")
  }

  async function commitRename() {
    if (!editingId) return
    const trimmed = editTitle.trim()
    if (trimmed) {
      const updated = await chatApi.updateConversation(agentId, editingId, { title: trimmed })
      setConversations((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
    }
    setEditingId(null)
    setEditTitle("")
  }

  function cancelRename() {
    setEditingId(null)
    setEditTitle("")
  }

  async function handleExport(conv: Conversation) {
    const res = await chatApi.getMessages(agentId, conv.id)
    const messages: Message[] = Array.isArray(res) ? res : (res as any).items ?? []
    const title = conv.title || "新对话"
    const lines = [`## ${title}\n`]
    for (const msg of messages) {
      const role = msg.role === "user" ? "用户" : "助手"
      lines.push(`**${role}:**\n${msg.content}\n`)
    }
    const md = lines.join("\n")
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${title}.md`
    a.click()
    URL.revokeObjectURL(url)
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
          {sorted.map((conv) => (
            <div
              key={conv.id}
              className={cn(
                "group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                activeId === conv.id && "bg-accent",
              )}
              onClick={() => onSelect(conv.id)}
              onDoubleClick={() => startRename(conv)}
            >
              <MessageCircle className="size-3.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                {editingId === conv.id ? (
                  <Input
                    ref={renameInputRef}
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitRename()
                      if (e.key === "Escape") cancelRename()
                    }}
                    onBlur={commitRename}
                    onClick={(e) => e.stopPropagation()}
                    className="h-5 px-1 py-0 text-sm"
                  />
                ) : (
                  <>
                    <p className="flex items-center gap-1 truncate">
                      {conv.is_pinned && <Pin className="size-3 shrink-0 text-muted-foreground" />}
                      {conv.title || "新对话"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      <TimeDisplay value={conv.updated_at} />
                    </p>
                  </>
                )}
              </div>
              {editingId !== conv.id && (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-6 opacity-0 group-hover:opacity-100"
                        onClick={(e) => e.stopPropagation()}
                      />
                    }
                  >
                    <MoreHorizontal className="size-3" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" side="bottom">
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation()
                        handleTogglePin(conv)
                      }}
                    >
                      <Pin className="size-4" />
                      {conv.is_pinned ? "取消置顶" : "置顶"}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation()
                        startRename(conv)
                      }}
                    >
                      <Pencil className="size-4" />
                      重命名
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation()
                        handleExport(conv)
                      }}
                    >
                      <Download className="size-4" />
                      导出
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      onClick={(e) => {
                        e.stopPropagation()
                        setDeleteTarget(conv.id)
                      }}
                    >
                      <Trash2 className="size-4" />
                      删除
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
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
