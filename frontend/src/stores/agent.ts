import { create } from "zustand"

interface AgentState {
  currentAgentId: string | null
  setCurrentAgent: (id: string | null) => void
}

export const useAgentStore = create<AgentState>((set) => ({
  currentAgentId: null,

  setCurrentAgent(id) {
    set({ currentAgentId: id })
  },
}))
