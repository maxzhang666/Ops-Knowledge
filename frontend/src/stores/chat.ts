import { create } from "zustand"
import type { Message, RetrievalChunk } from "@/api/chat"

interface ChatState {
  activeConversationId: string | null
  messages: Message[]
  isStreaming: boolean
  pendingContent: string
  thinkingSteps: string[]
  retrievalResults: RetrievalChunk[]

  setActiveConversation: (id: string | null) => void
  setMessages: (messages: Message[]) => void
  addMessage: (message: Message) => void
  startStreaming: () => void
  appendContent: (chunk: string) => void
  addThinking: (step: string) => void
  setRetrievalResults: (results: RetrievalChunk[]) => void
  finishStreaming: () => void
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  activeConversationId: null,
  messages: [],
  isStreaming: false,
  pendingContent: "",
  thinkingSteps: [],
  retrievalResults: [],

  setActiveConversation(id) {
    set({ activeConversationId: id, messages: [], pendingContent: "", thinkingSteps: [], retrievalResults: [] })
  },

  setMessages(messages) {
    set({ messages })
  },

  addMessage(message) {
    set((s) => ({ messages: [...s.messages, message] }))
  },

  startStreaming() {
    set({ isStreaming: true, pendingContent: "", thinkingSteps: [], retrievalResults: [] })
  },

  appendContent(chunk) {
    set((s) => ({ pendingContent: s.pendingContent + chunk }))
  },

  addThinking(step) {
    set((s) => ({ thinkingSteps: [...s.thinkingSteps, step] }))
  },

  setRetrievalResults(results) {
    set({ retrievalResults: results })
  },

  finishStreaming() {
    set({ isStreaming: false })
  },

  reset() {
    set({
      activeConversationId: null,
      messages: [],
      isStreaming: false,
      pendingContent: "",
      thinkingSteps: [],
      retrievalResults: [],
    })
  },
}))
