import { create } from "zustand"
import * as authApi from "@/api/auth"
import { api } from "@/api/client"
import type { User } from "@/api/types"

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  loadUser: () => Promise<void>
  setUser: (user: User) => void
  setTokens: (access: string, refresh: string) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!localStorage.getItem("access_token"),
  isLoading: false,

  async login(username, password) {
    const res = await authApi.login(username, password)
    localStorage.setItem("access_token", res.access_token)
    localStorage.setItem("refresh_token", res.refresh_token)
    const user = await authApi.getMe()
    set({ user, isAuthenticated: true })
  },

  async logout() {
    // Revoke server-side first so the jti is blacklisted. If the call fails
    // (e.g. network) we still proceed with local cleanup — the worst case is
    // the token remains valid until natural expiry.
    try { await api.post("/auth/logout") } catch { /* best-effort */ }
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    set({ user: null, isAuthenticated: false })
    window.location.href = "/login"
  },

  async loadUser() {
    set({ isLoading: true })
    try {
      const user = await authApi.getMe()
      set({ user, isAuthenticated: true, isLoading: false })
    } catch {
      set({ user: null, isAuthenticated: false, isLoading: false })
    }
  },

  setUser(user) {
    set({ user, isAuthenticated: true })
  },

  setTokens(access, refresh) {
    localStorage.setItem("access_token", access)
    localStorage.setItem("refresh_token", refresh)
    set({ isAuthenticated: true })
  },
}))
