import { useEffect } from "react"
import { useAuthStore } from "@/stores/auth"

export function useAuth() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const isLoading = useAuthStore((s) => s.isLoading)
  const user = useAuthStore((s) => s.user)
  const loadUser = useAuthStore((s) => s.loadUser)

  useEffect(() => {
    if (isAuthenticated && !user && !isLoading) {
      loadUser()
    }
  }, [isAuthenticated, user, isLoading, loadUser])

  return { isAuthenticated, isLoading, user }
}
