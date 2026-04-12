import { useCallback, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TimeDisplay } from "@/components/shared/time-display"
import { userApi } from "@/api/user"
import type { User } from "@/api/types"

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await userApi.list()
      setUsers(res.items)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">用户管理</h2>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">用户名</th>
              <th className="px-3 py-2">邮箱</th>
              <th className="px-3 py-2">角色</th>
              <th className="px-3 py-2">状态</th>
              <th className="px-3 py-2">认证方式</th>
              <th className="px-3 py-2">创建时间</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b last:border-0">
                <td className="px-3 py-2 font-medium">{u.username}</td>
                <td className="px-3 py-2 text-muted-foreground">{u.email}</td>
                <td className="px-3 py-2">
                  <Badge variant={u.role === "system_admin" ? "default" : "secondary"}>
                    {u.role === "system_admin" ? "管理员" : "用户"}
                  </Badge>
                </td>
                <td className="px-3 py-2">
                  <Badge variant={u.is_active ? "default" : "destructive"}>
                    {u.is_active ? "活跃" : "停用"}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-muted-foreground">{u.auth_provider}</td>
                <td className="px-3 py-2 text-muted-foreground">
                  <TimeDisplay value={u.created_at} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
