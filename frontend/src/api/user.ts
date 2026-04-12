import { api } from "./client"
import type { PaginatedResponse, User } from "./types"

export const userApi = {
  list(params?: Record<string, string>) {
    return api.get<PaginatedResponse<User>>("/users", params)
  },
}
