import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2, Copy, Check } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { TimeDisplay } from "@/components/shared/time-display"
import { api } from "@/api/client"

interface ApiKey {
  id: string
  raw_key: string
  key_prefix: string
  name: string
  scope: string
  is_active: boolean
  expires_at: string | null
  last_used_at: string | null
  created_at: string
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const [formName, setFormName] = useState("")
  const [createLoading, setCreateLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<ApiKey[]>("/system/api-keys")
      setKeys(Array.isArray(res) ? res : (res as any).items ?? [])
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
      await api.post<ApiKey>("/system/api-keys", { name: formName.trim() })
      setFormName("")
      setCreateOpen(false)
      toast.success("API 密钥已创建")
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建失败")
    } finally {
      setCreateLoading(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      // Full path is /system/api-keys/{id}/delete — previously missing the
      // /system prefix caused 404 on every delete attempt.
      await api.post(`/system/api-keys/${deleteTarget}/delete`)
      toast.success("已删除")
      setDeleteTarget(null)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  function handleCopy(key: ApiKey) {
    navigator.clipboard.writeText(key.raw_key)
    setCopiedId(key.id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">API 密钥</h2>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 size-4" />
          创建
        </Button>
      </div>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">名称</th>
              <th className="px-3 py-2">密钥</th>
              <th className="px-3 py-2">范围</th>
              <th className="px-3 py-2">过期时间</th>
              <th className="px-3 py-2">创建时间</th>
              <th className="px-3 py-2 w-20" />
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">暂无 API 密钥</td>
              </tr>
            ) : (
              keys.map((k) => (
                <tr key={k.id} className="border-b last:border-0">
                  <td className="px-3 py-2 font-medium">{k.name}</td>
                  <td className="px-3 py-2">
                    <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">{k.raw_key}</code>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="secondary">{k.scope}</Badge>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {k.expires_at ? <TimeDisplay value={k.expires_at} /> : "永不过期"}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    <TimeDisplay value={k.created_at} />
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="size-7" onClick={() => handleCopy(k)}>
                        {copiedId === k.id ? <Check className="size-3.5 text-green-500" /> : <Copy className="size-3.5" />}
                      </Button>
                      <Button variant="ghost" size="icon" className="size-7" onClick={() => setDeleteTarget(k.id)}>
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>创建 API 密钥</DialogTitle>
            <DialogDescription>创建一个新的 API 密钥用于外部集成</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label>名称 *</Label>
              <Input
                value={formName}
                onChange={(e: any) => setFormName(e.target.value)}
                placeholder="用于标识此密钥的名称"
                required
              />
            </div>
            <DialogFooter>
              <Button variant="outline" type="button" onClick={() => setCreateOpen(false)}>取消</Button>
              <Button type="submit" disabled={!formName.trim() || createLoading}>
                {createLoading ? "创建中..." : "创建"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v: boolean) => { if (!v) setDeleteTarget(null) }}
        title="删除 API 密钥"
        description="确认删除此 API 密钥？使用该密钥的所有集成将立即失效。"
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}
