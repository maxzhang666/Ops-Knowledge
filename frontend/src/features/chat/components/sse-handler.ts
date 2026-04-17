import { chatApi, streamChat, type SSEEvent } from "@/api/chat"
import { useChatStore } from "@/stores/chat"

let abortController: AbortController | null = null

export function abortStream() {
  abortController?.abort()
  abortController = null
}

async function _tryRecover(
  agentId: string,
  conversationId: string | undefined,
  messageId: string | null,
  pendingContent: string,
): Promise<void> {
  if (!messageId || !conversationId) return
  const s = useChatStore.getState()
  try {
    const msg = await chatApi.getMessage(agentId, conversationId, messageId)
    if (msg.status === "completed" && msg.content) {
      // Fill in what the client didn't receive before the disconnect
      if (msg.content.length > pendingContent.length && msg.content.startsWith(pendingContent)) {
        s.appendContent(msg.content.slice(pendingContent.length))
      } else if (msg.content && !pendingContent) {
        s.appendContent(msg.content)
      }
    } else if (msg.status === "generating") {
      s.appendContent("\n\n[连接中断，生成已停止。请重试以继续。]")
    } else if (msg.status === "error") {
      s.appendContent("\n\n[生成失败，请重试]")
    }
  } catch {
    s.appendContent(`\n\n[网络中断，无法恢复连接]`)
  }
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
  let assistantMessageId: string | null = null

  try {
    await streamChat(
      agentId,
      content,
      conversationId,
      (event: SSEEvent) => {
        const s = useChatStore.getState()
        const data = (() => {
          try { return JSON.parse(event.data) } catch { return {} }
        })()

        switch (event.event) {
          case "message_start":
            if (data.conversation_id) {
              newConversationId = data.conversation_id
              s.updateConversationId(data.conversation_id)
            }
            if (data.message_id) {
              assistantMessageId = data.message_id
            }
            break
          case "content_delta":
            s.appendContent(data.delta || "")
            break
          case "thinking":
            s.addThinking({ step: data.step, content: data.content })
            break
          case "retrieval_info":
            if (data.chunks) {
              s.setRetrievalResults(data.chunks)
            }
            break
          case "message_end":
            // Stream complete — metadata available in data.token_usage, data.trace_id
            break
        }
      },
      abortController.signal,
    )
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return
    // Network disconnect / SSE broken — attempt recovery via DB message state
    const s = useChatStore.getState()
    await _tryRecover(agentId, newConversationId, assistantMessageId, s.pendingContent ?? "")
  } finally {
    const s = useChatStore.getState()

    if (s.pendingContent) {
      s.addMessage({
        id: assistantMessageId ?? crypto.randomUUID(),
        conversation_id: newConversationId ?? "",
        role: "assistant",
        content: s.pendingContent,
        created_at: new Date().toISOString(),
      })
    }

    s.finishStreaming()
    abortController = null
  }
}
