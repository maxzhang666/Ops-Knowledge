import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2, Building2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { cn } from "@/lib/utils"
import { departmentApi, type Department, type Member } from "@/api/department"

export default function DepartmentsPage() {
  const [departments, setDepartments] = useState<Department[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [loading, setLoading] = useState(true)
  const [newDeptName, setNewDeptName] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const loadDepts = useCallback(async () => {
    setLoading(true)
    try {
      const data = await departmentApi.list()
      setDepartments(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDepts()
  }, [loadDepts])

  useEffect(() => {
    if (!selectedId) { setMembers([]); return }
    departmentApi.listMembers(selectedId).then(setMembers).catch(() => setMembers([]))
  }, [selectedId])

  async function handleCreateDept(e: React.FormEvent) {
    e.preventDefault()
    if (!newDeptName.trim()) return
    await departmentApi.create({ name: newDeptName.trim() })
    setNewDeptName("")
    loadDepts()
  }

  async function handleDeleteDept() {
    if (!deleteTarget) return
    await departmentApi.delete(deleteTarget)
    if (selectedId === deleteTarget) setSelectedId(null)
    loadDepts()
  }

  if (loading) return <LoadingSpinner className="py-16" />

  const selectedDept = departments.find((d) => d.id === selectedId)

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">部门管理</h2>

      <div className="flex gap-6">
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

          <ScrollArea className="h-80 rounded-md border">
            <div className="space-y-0.5 p-2">
              {departments.map((dept) => (
                <div
                  key={dept.id}
                  className={cn(
                    "group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                    selectedId === dept.id && "bg-accent",
                  )}
                  onClick={() => setSelectedId(dept.id)}
                >
                  <Building2 className="size-3.5 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate">{dept.name}</span>
                  <Badge variant="secondary" className="text-[10px]">{dept.member_count}</Badge>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-5 opacity-0 group-hover:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation()
                      setDeleteTarget(dept.id)
                    }}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>

        <div className="min-w-0 flex-1">
          {selectedDept ? (
            <div>
              <h3 className="mb-3 text-sm font-medium">{selectedDept.name} - 成员列表</h3>
              {members.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无成员</p>
              ) : (
                <div className="rounded-md border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                        <th className="px-3 py-2">用户名</th>
                        <th className="px-3 py-2">邮箱</th>
                        <th className="px-3 py-2">角色</th>
                      </tr>
                    </thead>
                    <tbody>
                      {members.map((m) => (
                        <tr key={m.id} className="border-b last:border-0">
                          <td className="px-3 py-2">{m.username}</td>
                          <td className="px-3 py-2 text-muted-foreground">{m.email}</td>
                          <td className="px-3 py-2">
                            <Badge variant="secondary">{m.role}</Badge>
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

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除部门"
        description="确认删除此部门？部门下的成员关系将被解除。"
        confirmText="删除"
        destructive
        onConfirm={handleDeleteDept}
      />
    </div>
  )
}
