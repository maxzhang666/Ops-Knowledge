import { create } from "zustand"

interface KnowledgeState {
  currentKBId: string | null
  selectedFolderId: string | null
  selectedDocId: string | null
  setCurrentKB: (id: string | null) => void
  setSelectedFolder: (id: string | null) => void
  setSelectedDoc: (id: string | null) => void
}

export const useKnowledgeStore = create<KnowledgeState>((set) => ({
  currentKBId: null,
  selectedFolderId: null,
  selectedDocId: null,

  setCurrentKB(id) {
    set({ currentKBId: id, selectedFolderId: null, selectedDocId: null })
  },

  setSelectedFolder(id) {
    set({ selectedFolderId: id, selectedDocId: null })
  },

  setSelectedDoc(id) {
    set({ selectedDocId: id })
  },
}))
