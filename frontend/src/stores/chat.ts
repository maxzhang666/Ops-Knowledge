import { create } from "zustand"
import type { Message, RetrievalChunk } from "@/api/chat"

interface ThinkingStep {
  step: number
  content: string
}

export interface OrchestratorDecision {
  matched_rule?: { id: string; match_type: string; handler_type: string } | null
  tried_rules?: string[]
  classifier?: { category: string; confidence: number; cached?: boolean } | null
}

export interface HandlerInvokedEvent {
  handler_type: string
  handler_id: string | null
  tool_name?: string
}

interface ChatState {
  activeConversationId: string | null
  messages: Message[]
  isStreaming: boolean
  pendingContent: string
  thinkingSteps: ThinkingStep[]
  retrievalResults: RetrievalChunk[]
  pendingMessageId: string | null
  pendingTraceId: string | null
  // Plan 31 debug mode — populated only when chat sent with ?debug=1
  orchestratorDecision: OrchestratorDecision | null
  handlerInvoked: HandlerInvokedEvent | null

  setActiveConversation: (id: string | null) => void
  updateConversationId: (id: string) => void
  setMessages: (messages: Message[]) => void
  addMessage: (message: Message) => void
  startStreaming: () => void
  appendContent: (delta: string) => void
  addThinking: (step: ThinkingStep) => void
  setRetrievalResults: (results: RetrievalChunk[]) => void
  setOrchestratorDecision: (data: OrchestratorDecision) => void
  setHandlerInvoked: (data: HandlerInvokedEvent) => void
  setStreamMeta: (messageId: string, conversationId: string) => void
  finishStreaming: (traceId?: string) => void
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  activeConversationId: null,
  messages: [],
  isStreaming: false,
  pendingContent: "",
  thinkingSteps: [],
  retrievalResults: [],
  pendingMessageId: null,
  pendingTraceId: null,
  orchestratorDecision: null,
  handlerInvoked: null,

  setActiveConversation(id) {
    set({
      activeConversationId: id,
      messages: [],
      pendingContent: "",
      thinkingSteps: [],
      retrievalResults: [],
      orchestratorDecision: null,
      handlerInvoked: null,
    })
  },

  updateConversationId(id) {
    set({ activeConversationId: id })
  },

  setMessages(messages) {
    set({ messages })
  },

  addMessage(message) {
    set((s) => ({ messages: [...s.messages, message] }))
  },

  startStreaming() {
    set({
      isStreaming: true,
      pendingContent: "",
      thinkingSteps: [],
      retrievalResults: [],
      pendingMessageId: null,
      pendingTraceId: null,
      orchestratorDecision: null,
      handlerInvoked: null,
    })
  },

  setOrchestratorDecision(data) {
    set({ orchestratorDecision: data })
  },

  setHandlerInvoked(data) {
    set({ handlerInvoked: data })
  },

  appendContent(delta) {
    set((s) => ({ pendingContent: s.pendingContent + delta }))
  },

  addThinking(step) {
    set((s) => ({ thinkingSteps: [...s.thinkingSteps, step] }))
  },

  setRetrievalResults(results) {
    set({ retrievalResults: results })
  },

  setStreamMeta(messageId, conversationId) {
    set({ pendingMessageId: messageId, activeConversationId: conversationId })
  },

  finishStreaming(traceId) {
    set({ isStreaming: false, pendingTraceId: traceId ?? null })
  },

  reset() {
    set({
      activeConversationId: null,
      messages: [],
      isStreaming: false,
      pendingContent: "",
      thinkingSteps: [],
      retrievalResults: [],
      pendingMessageId: null,
      pendingTraceId: null,
      orchestratorDecision: null,
      handlerInvoked: null,
    })
  },
}))
