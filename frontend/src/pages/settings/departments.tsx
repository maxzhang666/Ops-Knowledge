import { useCallback, useEffect, useMemo, useState } from "react"
import { Plus, Trash2, Building2, UserPlus, MoreHorizontal } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { cn } from "@/lib/utils"
import { departmentApi, type Department, type Member } from "@/api/department"
import { userApi } from "@/api/user"
import type { User } from "@/api/types"

type DeptRole = "dept_admin" | "editor" | "viewer"

const ROLE_LABELS: Record<DeptRole, string> = {
  dept_admin: "部门管理员",
  editor: "编辑者",
  viewer: "查看者",
}

export default function DepartmentsPage() {
  const [departments, setDepartments] = useState<Department[]>([])
  const [allUsers, setAllUsers] = useState<User[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [loading, setLoading] = useState(true)
  const [newDeptName, setNewDeptName] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  // Add member dialog
  const [addOpen, setAddOpen] = useState(false)
  const [addUserId, setAddUserId] = useState<string>("")
  const [addRole, setAddRole] = useState<DeptRole>("viewer")
  const [addIsPrimary, setAddIsPrimary] = useState(true)
  const [adding, setAdding] = useState(false)

  // Remove member confirm
  const [removeTarget, setRemoveTarget] = useState<Member | null>(null)

  const loadDepts = useCallback(async () => {
    setLoading(true)
    try {
      const data = await departmentApi.list()
      setDepartments(data)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadUsers = useCallback(async () => {
    try {
      const res = await userApi.list({ page_size: "100" })
      setAllUsers(res.items ?? [])
    } catch { /* ignore — non-admin may not have access */ }
  }, [])

  const loadMembers = useCallback(async (deptId: string) => {
    try {
      const m = await departmentApi.listMembers(deptId)
      setMembers(m)
    } catch {
      setMembers([])
    }
  }, [])

  useEffect(() => {
    loadDepts()
    loadUsers()
  }, [loadDepts, loadUsers])

  useEffect(() => {
    if (!selectedId) { setMembers([]); return }
    loadMembers(selectedId)
  }, [selectedId, loadMembers])

  async function handleCreateDept(e: React.FormEvent) {
    e.preventDefault()
    if (!newDeptName.trim()) return
    try {
      await departmentApi.create({ name: newDeptName.trim() })
      toast.success("部门已创建")
      setNewDeptName("")
      loadDepts()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建失败")
    }
  }

  async function handleDeleteDept() {
    if (!deleteTarget) return
    try {
      await departmentApi.delete(deleteTarget)
      toast.success("部门已删除")
      if (selectedId === deleteTarget) setSelectedId(null)
      loadDepts()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  // Users who are NOT already members of the selected department
  const candidateUsers = useMemo(() => {
    const inDept = new Set(members.map((m) => m.user_id))
    return allUsers.filter((u) => !inDept.has(u.id))
  }, [allUsers, members])

  function openAddDialog() {
    setAddUserId(candidateUsers[0]?.id ?? "")
    setAddRole("viewer")
    setAddIsPrimary(true)
    setAddOpen(true)
  }

  async function handleAddMember() {
    if (!selectedId || !addUserId) return
    setAdding(true)
    try {
      await departmentApi.addMember(selectedId, {
        user_id: addUserId,
        role: addRole,
        is_primary: addIsPrimary,
      })
      toast.success("已添加成员")
      setAddOpen(false)
      loadMembers(selectedId)
      loadDepts()  // member_count 可能变化
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "添加失败")
    } finally {
      setAdding(false)
    }
  }

  async function handleUpdateRole(member: Member, role: DeptRole) {
    if (!selectedId || role === member.role) return
    try {
      await departmentApi.updateMemberRole(selectedId, member.user_id, { role })
      toast.success("角色已更新")
      loadMembers(selectedId)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新失败")
    }
  }

  async function handleRemoveMember() {
    if (!selectedId || !removeTarget) return
    try {
      await departmentApi.removeMember(selectedId, removeTarget.user_id)
      toast.success("已移除成员")
      setRemoveTarget(null)
      loadMembers(selectedId)
      loadDepts()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "移除失败")
    }
  }

  if (loading) return <LoadingSpinner className="py-16" />

  const selectedDept = departments.find((d) => d.id === selectedId)

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">部门管理</h2>

      <div className="flex gap-6">
        {/* Left: department list */}
        <div className="w-64 shrink-0">
          <form onSubmit={handleCreateDept} className="mb-3 flex gap-2">
            <Input
              value={newDeptName}
              onChange={(e) => setNewDeptName(e.target.value)}
              placeholder="新部门名称"
              className="text-sm"
            />
            <Button type="submit" size="icon" disabled={!newDeptName.trim()}>
              <Plus className="size-4" />
            </Button>
          </form>

          <ScrollArea className="h-[28rem] rounded-md border">
            <div className="space-y-0.5 p-2">
              {departments.map((dept) => (
                <div
                  key={dept.id}
                  className={cn(
                    "group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                    selectedId === dept.id && "bg-accent font-medium text-accent-foreground",
                  )}
                  onClick={() => setSelectedId(dept.id)}
                >
                  <Building2 className="size-3.5 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate">{dept.name}</span>
                  {dept.member_count != null && (
                    <Badge variant="secondary" className="text-[10px]">{dept.member_count}</Badge>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-5 opacity-0 group-hover:opacity-100"
                    onClick={(e) => { e.stopPropagation(); setDeleteTarget(dept.id) }}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* Right: members */}
        <div className="min-w-0 flex-1">
          {selectedDept ? (
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-medium">
                  {selectedDept.name} · 成员 <span className="text-muted-foreground">({members.length})</span>
                </h3>
                <Button size="sm" onClick={openAddDialog} disabled={candidateUsers.length === 0}>
                  <UserPlus className="mr-1 size-3.5" /> 添加成员
                </Button>
              </div>

              {members.length === 0 ? (
                <div className="rounded-md border border-dashed py-10 text-center text-sm text-muted-foreground">
                  暂无成员，点击「添加成员」把用户加入此部门
                </div>
              ) : (
                <div className="overflow-hidden rounded-md border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                        <th className="px-3 py-2">用户名</th>
                        <th className="px-3 py-2">邮箱</th>
                        <th className="w-36 px-3 py-2">角色</th>
                        <th className="w-16 px-3 py-2 text-center">主部门</th>
                        <th className="w-12 px-3 py-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {members.map((m) => (
                        <tr key={m.id} className="border-b last:border-0 hover:bg-muted/30">
                          <td className="px-3 py-2">{m.username}</td>
                          <td className="px-3 py-2 text-muted-foreground">{m.email}</td>
                          <td className="px-3 py-2">
                            <Select
                              value={m.role}
                              onValueChange={(v) => v && handleUpdateRole(m, v as DeptRole)}
                            >
                              <SelectTrigger className="h-7 text-xs">
                                <span>{ROLE_LABELS[m.role]}</span>
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="dept_admin">{ROLE_LABELS.dept_admin}</SelectItem>
                                <SelectItem value="editor">{ROLE_LABELS.editor}</SelectItem>
                                <SelectItem value="viewer">{ROLE_LABELS.viewer}</SelectItem>
                              </SelectContent>
                            </Select>
                          </td>
                          <td className="px-3 py-2 text-center text-muted-foreground">
                            {m.is_primary ? "✓" : "—"}
                          </td>
                          <td className="px-3 py-2 text-right">
                            <DropdownMenu>
                              <DropdownMenuTrigger
                                render={
                                  <button
                                    type="button"
                                    className="inline-flex size-7 items-center justify-center rounded hover:bg-accent"
                                    title="操作"
                                  />
                                }
                              >
                                <MoreHorizontal className="size-3.5" />
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end" className="text-sm">
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  onClick={() => setRemoveTarget(m)}
                                  className="text-destructive"
                                >
                                  <Trash2 className="mr-2 size-3.5" /> 从部门移除
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">选择一个部门查看成员</p>
          )}
        </div>
      </div>

      {/* Add member dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加成员</DialogTitle>
            <DialogDescription>
              把用户加入 <span className="font-medium">{selectedDept?.name}</span>。同一用户只能在一个部门作为主部门。
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-2">
            <div className="flex flex-col gap-1.5">
              <Label>选择用户</Label>
              <Select value={addUserId || undefined} onValueChange={(v) => v && setAddUserId(v)}>
                <SelectTrigger>
                  {addUserId
                    ? <span>{allUsers.find((u) => u.id === addUserId)?.username ?? addUserId}</span>
                    : <SelectValue placeholder="选择用户" />}
                </SelectTrigger>
                <SelectContent>
                  {candidateUsers.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {u.username} <span className="text-muted-foreground">({u.email})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {candidateUsers.length === 0 && (
                <p className="text-xs text-muted-foreground">所有用户都已在此部门</p>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>角色</Label>
              <Select value={addRole} onValueChange={(v) => v && setAddRole(v as DeptRole)}>
                <SelectTrigger>
                  <span>{ROLE_LABELS[addRole]}</span>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="dept_admin">{ROLE_LABELS.dept_admin}</SelectItem>
                  <SelectItem value="editor">{ROLE_LABELS.editor}</SelectItem>
                  <SelectItem value="viewer">{ROLE_LABELS.viewer}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={addIsPrimary} onCheckedChange={(v) => setAddIsPrimary(v as boolean)} />
              <Label className="text-sm">设为该用户的主部门</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>取消</Button>
            <Button onClick={handleAddMember} disabled={!addUserId || adding}>
              {adding ? "添加中..." : "添加"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除部门"
        description="确认删除此部门？部门下的成员关系将被解除。"
        confirmText="删除"
        destructive
        onConfirm={handleDeleteDept}
      />

      <ConfirmDialog
        open={!!removeTarget}
        onOpenChange={(v) => { if (!v) setRemoveTarget(null) }}
        title="从部门移除成员"
        description={`确认从 "${selectedDept?.name}" 移除成员 "${removeTarget?.username}"？`}
        confirmText="移除"
        destructive
        onConfirm={handleRemoveMember}
      />
    </div>
  )
}
