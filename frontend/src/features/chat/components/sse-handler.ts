import { streamChat, type SSEEvent } from "@/api/chat"
import { useChatStore } from "@/stores/chat"

let abortController: AbortController | null = null

export function abortStream() {
  abortController?.abort()
  abortController = null
}

export async function sendMessage(agentId: string, content: string, conversationId?: string) {
  const store = useChatStore.getState()
  store.startStreaming()

  store.addMessage({
    id: crypto.randomUUID(),
    conversation_id: conversationId ?? "",
    role: "user",
    content,
    created_at: new Date().toISOString(),
  })

  abortController = new AbortController()

  let newConversationId = conversationId

  try {
    await streamChat(
      agentId,
      content,
      conversationId,
      (event: SSEEvent) => {
        const s = useChatStore.getState()
        switch (event.event) {
          case "content":
            s.appendContent(event.data)
            break
          case "thinking":
            s.addThinking(event.data)
            break
          case "retrieval": {
            try {
              const results = JSON.parse(event.data)
              s.setRetrievalResults(results)
            } catch { /* ignore parse errors */ }
            break
          }
          case "done": {
            try {
              const meta = JSON.parse(event.data)
              if (meta.conversation_id) {
                newConversationId = meta.conversation_id
                s.setActiveConversation(meta.conversation_id)
              }
            } catch { /* ignore */ }
            break
          }
          case "error":
            s.appendContent(`\n\n[Error: ${event.data}]`)
            break
        }
      },
      abortController.signal,
    )
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return
    const s = useChatStore.getState()
    s.appendContent(`\n\n[Error: ${err instanceof Error ? err.message : "Unknown error"}]`)
  } finally {
    const s = useChatStore.getState()

    if (s.pendingContent) {
      s.addMessage({
        id: crypto.randomUUID(),
        conversation_id: newConversationId ?? "",
        role: "assistant",
        content: s.pendingContent,
        thinking_steps: s.thinkingSteps.length > 0 ? [...s.thinkingSteps] : undefined,
        retrieval_results: s.retrievalResults.length > 0 ? [...s.retrievalResults] : undefined,
        created_at: new Date().toISOString(),
      })
    }

    s.finishStreaming()
    abortController = null
  }
}
