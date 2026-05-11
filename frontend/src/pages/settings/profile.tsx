import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { useAuthStore } from "@/stores/auth"
import { api } from "@/api/client"

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user)
  const [oldPassword, setOldPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault()
    setErrorMsg("")

    if (newPassword !== confirmPassword) {
      setErrorMsg("两次输入的密码不一致")
      return
    }
    if (newPassword.length < 6) {
      setErrorMsg("密码长度至少 6 位")
      return
    }

    setLoading(true)
    try {
      await api.post("/auth/change-password", {
        current_password: oldPassword,
        new_password: newPassword,
      })
      toast.success("密码修改成功")
      setOldPassword("")
      setNewPassword("")
      setConfirmPassword("")
    } catch (err) {
      const msg = err instanceof Error ? err.message : "修改失败"
      setErrorMsg(msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-lg">
      <h2 className="mb-4 text-lg font-semibold">个人设置</h2>

      <div className="space-y-3">
        <div className="flex flex-col gap-1">
          <Label className="text-muted-foreground">用户名</Label>
          <p className="text-sm font-medium">{user?.username}</p>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-muted-foreground">邮箱</Label>
          <p className="text-sm font-medium">{user?.email}</p>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-muted-foreground">角色</Label>
          <p className="text-sm font-medium">{user?.role === "system_admin" ? "管理员" : "用户"}</p>
        </div>
      </div>

      <Separator className="my-6" />

      <h3 className="mb-4 text-sm font-medium">修改密码</h3>
      <form onSubmit={handleChangePassword} className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor="old-pw">当前密码</Label>
          <Input
            id="old-pw"
            type="password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            required
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="new-pw">新密码</Label>
          <Input
            id="new-pw"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="confirm-pw">确认新密码</Label>
          <Input
            id="confirm-pw"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
        </div>
        {errorMsg && (
          <p className="text-sm text-red-600">{errorMsg}</p>
        )}
        <div>
          <Button type="submit" disabled={loading}>
            {loading ? "修改中..." : "修改密码"}
          </Button>
        </div>
      </form>
    </div>
  )
}
