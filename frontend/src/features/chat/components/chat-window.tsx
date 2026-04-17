import { useCallback, useEffect, useRef, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { MessageBubble } from "./message-bubble"
import { ThinkingBlock } from "./thinking-block"
import { ReferencePanel } from "./reference-panel"
import { ChatInput } from "./chat-input"
import { sendMessage, abortStream } from "./sse-handler"
import { useChatStore } from "@/stores/chat"
import { chatApi } from "@/api/chat"
import { Bot } from "lucide-react"

interface ChatWindowProps {
  agentId: string
  conversationId: string | null
  welcomeMessage?: string
}

export function ChatWindow({ agentId, conversationId, welcomeMessage }: ChatWindowProps) {
  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const pendingContent = useChatStore((s) => s.pendingContent)
  const thinkingSteps = useChatStore((s) => s.thinkingSteps)
  const retrievalResults = useChatStore((s) => s.retrievalResults)
  const setMessages = useChatStore((s) => s.setMessages)

  const [refOpen, setRefOpen] = useState(false)
  const [refHighlight, setRefHighlight] = useState<number | undefined>()
  const bottomRef = useRef<HTMLDivElement>(null)

  const loadMessages = useCallback(async () => {
    if (!conversationId) {
      setMessages([])
      return
    }
    const res = await chatApi.getMessages(agentId, conversationId, { page_size: "100" })
    const list = Array.isArray(res) ? res : (res as any).items ?? []
    setMessages(list)
  }, [agentId, conversationId, setMessages])

  // Load messages on conversationId change — but NOT during a live stream,
  // because the SSE pipeline itself updates activeConversationId mid-flight
  // (via message_start), and re-loading here would overwrite the streaming
  // state. Skipping load while streaming keeps the ongoing session intact.
  useEffect(() => {
    if (isStreaming) return
    loadMessages()
  }, [loadMessages, isStreaming])

  // Abort the stream only on unmount — NOT on conversationId change, which
  // would terminate the stream that just updated conversationId itself.
  useEffect(() => {
    return () => { abortStream() }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, pendingContent])

  function handleSend(content: string) {
    sendMessage(agentId, content, conversationId ?? undefined)
  }

  function handleCitation(index: number) {
    setRefHighlight(index)
    setRefOpen(true)
  }

  const activeRetrievalResults = isStreaming ? retrievalResults : []

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <ScrollArea className="min-h-0 flex-1 p-4">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {messages.length === 0 && !isStreaming && welcomeMessage && (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Bot className="size-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">{welcomeMessage}</p>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id}>
              <MessageBubble message={msg} onCitationClick={handleCitation} />
            </div>
          ))}

          {isStreaming && (
            <div>
              {thinkingSteps.length > 0 && (
                <ThinkingBlock steps={thinkingSteps.map((t) => t.content)} />
              )}
              {pendingContent && (
                <div className="flex justify-start">
                  <div className="max-w-[75%] rounded-2xl bg-muted px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap">
                    {pendingContent}
                    <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-foreground" />
                  </div>
                </div>
              )}
              {!pendingContent && (
                <div className="flex justify-start">
                  <div className="rounded-2xl bg-muted px-4 py-2.5">
                    <span className="flex gap-1">
                      <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:0ms]" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:150ms]" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:300ms]" />
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <ChatInput onSend={handleSend} disabled={isStreaming} />

      <ReferencePanel
        open={refOpen}
        onOpenChange={setRefOpen}
        chunks={activeRetrievalResults}
        highlightIndex={refHighlight}
      />
    </div>
  )
}
