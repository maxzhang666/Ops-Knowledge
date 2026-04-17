import { api } from "./client"
import type { InitStatus, TokenResponse, User } from "./types"

export function login(username: string, password: string) {
  return api.post<TokenResponse>("/auth/login", { username, password })
}

export function register(data: { username: string; email: string; password: string }) {
  return api.post<User>("/auth/register", data)
}

export function getMe() {
  return api.get<User>("/auth/me")
}

export function refresh(refreshToken: string) {
  return api.post<TokenResponse>("/auth/refresh", { refresh_token: refreshToken })
}

export function initStatus() {
  return api.get<InitStatus>("/system/init/status")
}

export function initSystem(data: { username: string; email: string; password: string }) {
  return api.post<User>("/system/init", data)
}
