import { api } from "./client"
import type { PaginatedResponse } from "./types"

export interface Conversation {
  id: string
  agent_id: string
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface RetrievalChunk {
  chunk_id: string
  content: string
  score: number
  document_name: string
}

export interface Message {
  id: string
  conversation_id: string
  role: "user" | "assistant"
  content: string
  thinking_steps?: string[]
  retrieval_results?: RetrievalChunk[]
  created_at: string
}

export const chatApi = {
  listConversations(agentId: string, params?: Record<string, string>) {
    return api.get<PaginatedResponse<Conversation>>(`/agents/${agentId}/conversations`, params)
  },

  createConversation(agentId: string) {
    return api.post<Conversation>(`/agents/${agentId}/conversations`)
  },

  getMessages(conversationId: string, params?: Record<string, string>) {
    return api.get<PaginatedResponse<Message>>(`/conversations/${conversationId}/messages`, params)
  },

  deleteConversation(conversationId: string) {
    return api.delete<void>(`/conversations/${conversationId}`)
  },
}

export interface SSEEvent {
  event: "content" | "thinking" | "retrieval" | "done" | "error"
  data: string
}

export async function streamChat(
  agentId: string,
  content: string,
  conversationId?: string,
  onEvent?: (event: SSEEvent) => void,
  signal?: AbortSignal,
) {
  const token = localStorage.getItem("access_token")
  const res = await fetch(`/api/v1/agents/${agentId}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content, conversation_id: conversationId }),
    signal,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error("No response body")

  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""

    let currentEvent = ""
    for (const line of lines) {
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim()
      } else if (line.startsWith("data:")) {
        const data = line.slice(5).trim()
        if (currentEvent && onEvent) {
          onEvent({ event: currentEvent as SSEEvent["event"], data })
        }
      }
    }
  }
}
