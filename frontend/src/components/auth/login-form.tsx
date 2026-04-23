import { useEffect, useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { getSsoConfig } from "@/api/auth"
import { useAuthStore } from "@/stores/auth"

export function LoginForm() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [ssoEnabled, setSsoEnabled] = useState(false)
  const [ssoLabel, setSsoLabel] = useState("使用 SSO 登录")
  const login = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  useEffect(() => {
    // Config endpoint is public + tolerant; failure → SSO stays hidden.
    getSsoConfig()
      .then((c) => {
        if (c.enabled) {
          setSsoEnabled(true)
          if (c.button_label) setSsoLabel(c.button_label)
        }
      })
      .catch(() => { /* ignore — no SSO in this deployment */ })
  }, [])

  function handleSsoLogin() {
    const returnTo = `${window.location.origin}/login/callback`
    window.location.href = `/api/v1/auth/sso/login?return_to=${encodeURIComponent(returnTo)}`
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      await login(username, password)
      navigate("/", { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-2xl">登录</CardTitle>
        <CardDescription>输入您的账号信息</CardDescription>
      </CardHeader>
      <CardContent>
        {ssoEnabled && (
          <div className="mb-4 flex flex-col gap-3">
            <Button type="button" variant="outline" className="w-full" onClick={handleSsoLogin}>
              {ssoLabel}
            </Button>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Separator className="flex-1" />
              <span>或</span>
              <Separator className="flex-1" />
            </div>
          </div>
        )}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="username">用户名</Label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={loading} className="w-full">
            {loading ? "登录中..." : "登录"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
