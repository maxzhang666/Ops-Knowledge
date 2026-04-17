import { api } from "./client"
import type { PaginatedResponse, User } from "./types"

interface CreateUserPayload {
  username: string
  email: string
  password: string
  role: "system_admin" | "user"
}

interface UpdateUserPayload {
  username?: string
  email?: string
  role?: "system_admin" | "user"
  is_active?: boolean
}

export const userApi = {
  list(params?: Record<string, string>) {
    return api.get<PaginatedResponse<User>>("/system/users", params)
  },

  create(data: CreateUserPayload) {
    return api.post<User>("/system/users", data)
  },

  update(id: string, data: UpdateUserPayload) {
    return api.post<User>(`/system/users/${id}/update`, data)
  },

  delete(id: string) {
    return api.post<void>(`/system/users/${id}/delete`)
  },
}
