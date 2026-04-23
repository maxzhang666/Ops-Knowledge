import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { useAuthStore } from "@/stores/auth"

/**
 * SSO callback landing page.
 *
 * Backend issues a 302 to `/login/callback#access_token=...&refresh_token=...`.
 * Fragment is client-only (never hits server logs). We parse, persist to
 * localStorage via the auth store, clean the URL, and route to home.
 */
export default function LoginCallbackPage() {
  const navigate = useNavigate()
  const setTokens = useAuthStore((s) => s.setTokens)

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""))
    const access = params.get("access_token")
    const refresh = params.get("refresh_token")
    if (!access || !refresh) {
      navigate("/login?sso_error=missing_tokens", { replace: true })
      return
    }
    setTokens(access, refresh)
    // Drop the fragment from browser history so the token pair isn't visible
    // after a page refresh.
    window.history.replaceState(null, "", window.location.pathname)
    navigate("/", { replace: true })
  }, [navigate, setTokens])

  return (
    <div className="flex min-h-svh items-center justify-center bg-background">
      <p className="text-sm text-muted-foreground">登录中…</p>
    </div>
  )
}
