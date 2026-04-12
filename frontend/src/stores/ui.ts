import { create } from "zustand"

type Theme = "light" | "dark" | "system"

interface UiState {
  sidebarCollapsed: boolean
  theme: Theme
  toggleSidebar: () => void
  setTheme: (theme: Theme) => void
}

export const useUiStore = create<UiState>((set) => ({
  sidebarCollapsed: localStorage.getItem("sidebar_collapsed") === "true",
  theme: (localStorage.getItem("theme") as Theme) || "system",

  toggleSidebar() {
    set((s) => {
      const next = !s.sidebarCollapsed
      localStorage.setItem("sidebar_collapsed", String(next))
      return { sidebarCollapsed: next }
    })
  },

  setTheme(theme) {
    localStorage.setItem("theme", theme)
    set({ theme })
  },
}))
