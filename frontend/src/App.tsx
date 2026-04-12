import { useEffect, useState } from "react"
import { RouterProvider } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { initStatus } from "@/api/auth"
import { useAuthStore } from "@/stores/auth"
import { router } from "@/router"
import { LoadingSpinner } from "@/components/shared/loading-spinner"

export default function App() {
  const [ready, setReady] = useState(false)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const loadUser = useAuthStore((s) => s.loadUser)

  useEffect(() => {
    async function bootstrap() {
      try {
        const status = await initStatus()
        if (!status.initialized) {
          router.navigate("/init", { replace: true })
        } else if (isAuthenticated) {
          await loadUser()
        }
      } catch {
        // API unreachable — proceed to let router handle it
      } finally {
        setReady(true)
      }
    }
    bootstrap()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!ready) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <>
      <RouterProvider router={router} />
      <Toaster />
    </>
  )
}
