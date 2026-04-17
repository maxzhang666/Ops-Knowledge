import { useCallback, useEffect, useState } from "react"
import { Plus, Pencil, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { TimeDisplay } from "@/components/shared/time-display"
import { userApi } from "@/api/user"
import type { User } from "@/api/types"

type Role = "system_admin" | "user"
const ROLE_LABELS: Record<string, string> = { system_admin: "系统管理员", user: "普通用户" }

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)

  // Create dialog
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState({ username: "", email: "", password: "", role: "user" as Role })
  const [createLoading, setCreateLoading] = useState(false)

  // Edit dialog
  const [editTarget, setEditTarget] = useState<User | null>(null)
  const [editForm, setEditForm] = useState({ username: "", email: "", role: "user" as Role, is_active: true })
  const [editLoading, setEditLoading] = useState(false)

  // Delete dialog
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null)

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

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreateLoading(true)
    try {
      await userApi.create({
        username: createForm.username.trim(),
        email: createForm.email.trim(),
        password: createForm.password,
        role: createForm.role,
      })
      toast.success("用户创建成功")
      setCreateOpen(false)
      setCreateForm({ username: "", email: "", password: "", role: "user" })
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建失败")
    } finally {
      setCreateLoading(false)
    }
  }

  function openEdit(user: User) {
    setEditTarget(user)
    setEditForm({ username: user.username, email: user.email, role: user.role, is_active: user.is_active })
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault()
    if (!editTarget) return
    setEditLoading(true)
    try {
      await userApi.update(editTarget.id, {
        username: editForm.username.trim(),
        email: editForm.email.trim(),
        role: editForm.role,
        is_active: editForm.is_active,
      })
      toast.success("用户信息已更新")
      setEditTarget(null)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新失败")
    } finally {
      setEditLoading(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await userApi.delete(deleteTarget.id)
      toast.success("用户已删除")
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">用户管理</h2>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 size-4" />
          新建用户
        </Button>
      </div>

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
              <th className="px-3 py-2 text-right">操作</th>
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
                <td className="px-3 py-2 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <Button variant="ghost" size="icon-sm" onClick={() => openEdit(u)}>
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon-sm" onClick={() => setDeleteTarget(u)}>
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Create User Dialog */}
      <Dialog
        open={createOpen}
        onOpenChange={(v) => {
          setCreateOpen(v)
          if (!v) setCreateForm({ username: "", email: "", password: "", role: "user" })
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建用户</DialogTitle>
            <DialogDescription>创建新的系统用户</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label>用户名 *</Label>
              <Input
                value={createForm.username}
                onChange={(e) => setCreateForm((f) => ({ ...f, username: e.target.value }))}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>邮箱 *</Label>
              <Input
                type="email"
                value={createForm.email}
                onChange={(e) => setCreateForm((f) => ({ ...f, email: e.target.value }))}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>密码 *</Label>
              <Input
                type="password"
                value={createForm.password}
                onChange={(e) => setCreateForm((f) => ({ ...f, password: e.target.value }))}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>角色 *</Label>
              <Select value={createForm.role} onValueChange={(v) => v && setCreateForm((f) => ({ ...f, role: v as Role }))}>
                <SelectTrigger className="w-full">
                  {createForm.role
                    ? <span>{ROLE_LABELS[createForm.role] ?? createForm.role}</span>
                    : <SelectValue placeholder="选择角色" />}
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">普通用户</SelectItem>
                  <SelectItem value="system_admin">系统管理员</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button variant="outline" type="button" onClick={() => setCreateOpen(false)}>取消</Button>
              <Button type="submit" disabled={createLoading}>
                {createLoading ? "创建中..." : "创建"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog
        open={!!editTarget}
        onOpenChange={(v) => { if (!v) setEditTarget(null) }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑用户</DialogTitle>
            <DialogDescription>修改用户信息</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEdit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label>用户名 *</Label>
              <Input
                value={editForm.username}
                onChange={(e) => setEditForm((f) => ({ ...f, username: e.target.value }))}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>邮箱 *</Label>
              <Input
                type="email"
                value={editForm.email}
                onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>角色 *</Label>
              <Select value={editForm.role} onValueChange={(v) => v && setEditForm((f) => ({ ...f, role: v as Role }))}>
                <SelectTrigger className="w-full">
                  {editForm.role
                    ? <span>{ROLE_LABELS[editForm.role] ?? editForm.role}</span>
                    : <SelectValue placeholder="选择角色" />}
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">普通用户</SelectItem>
                  <SelectItem value="system_admin">系统管理员</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <Label>启用状态</Label>
              <Switch
                checked={editForm.is_active}
                onCheckedChange={(v) => setEditForm((f) => ({ ...f, is_active: v }))}
              />
            </div>
            <DialogFooter>
              <Button variant="outline" type="button" onClick={() => setEditTarget(null)}>取消</Button>
              <Button type="submit" disabled={editLoading}>
                {editLoading ? "保存中..." : "保存"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除用户"
        description={`确认删除用户「${deleteTarget?.username}」？此操作不可撤销。`}
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}
