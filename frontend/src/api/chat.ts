import { api } from "./client"
import type { PaginatedResponse } from "./types"

export interface Conversation {
  id: string
  agent_id: string
  title: string | null
  user_id: string
  message_count: number
  is_pinned: boolean
  created_at: string
  updated_at: string
}

export interface RetrievalChunk {
  id: string
  content_preview: string
  score: number
  document_title: string
  // Plan 32 — populated by chat pipeline so reference panel can deep-link to the source
  document_id?: string | null
  source_kb_id?: string | null
}

export interface Message {
  id: string
  conversation_id: string
  role: "user" | "assistant" | "system"
  content: string
  status?: "generating" | "completed" | "error"
  metadata?: Record<string, unknown> | null
  token_usage?: Record<string, number> | null
  trace_id?: string | null
  feedback?: number | null
  created_at: string
}

export const chatApi = {
  listConversations(agentId: string, params?: Record<string, string>) {
    return api.get<PaginatedResponse<Conversation>>(`/agents/${agentId}/conversations`, params)
  },

  createConversation(agentId: string) {
    return api.post<Conversation>(`/agents/${agentId}/conversations`)
  },

  getMessages(agentId: string, conversationId: string, params?: Record<string, string>) {
    return api.get<Message[]>(`/agents/${agentId}/conversations/${conversationId}/messages`, params)
  },

  getMessage(agentId: string, conversationId: string, messageId: string) {
    return api.get<Message>(
      `/agents/${agentId}/conversations/${conversationId}/messages/${messageId}`,
    )
  },

  updateConversation(agentId: string, conversationId: string, data: { title?: string; is_pinned?: boolean }) {
    return api.post<Conversation>(`/agents/${agentId}/conversations/${conversationId}/update`, data)
  },

  deleteConversation(agentId: string, conversationId: string) {
    return api.post<void>(`/agents/${agentId}/conversations/${conversationId}/delete`)
  },
}

export interface SSEEvent {
  // Plan 31: Orchestrator adds `orchestrator_decision` (debug mode) and
  // `handler_invoked` events — everything else same as Simple/Workflow.
  event:
    | "message_start"
    | "thinking"
    | "content_delta"
    | "retrieval_info"
    | "message_end"
    | "orchestrator_decision"
    | "handler_invoked"
  data: string
}

export interface StreamChatOpts {
  metadata?: Record<string, unknown>
  debug?: boolean
}

export async function streamChat(
  agentId: string,
  content: string,
  conversationId?: string,
  onEvent?: (event: SSEEvent) => void,
  signal?: AbortSignal,
  opts?: StreamChatOpts,
) {
  const token = localStorage.getItem("access_token")
  const body: Record<string, unknown> = {
    content,
    conversation_id: conversationId,
  }
  if (opts?.metadata) body.metadata = opts.metadata
  if (opts?.debug) body.debug = true
  const res = await fetch(`/api/v1/agents/${agentId}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
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
