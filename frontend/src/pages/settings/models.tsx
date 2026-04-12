import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2, PlayCircle, CheckCircle2, XCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { modelApi, type ModelProvider } from "@/api/model"

export default function ModelsPage() {
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; msg: string }>>({})

  // Create form
  const [formName, setFormName] = useState("")
  const [formType, setFormType] = useState("")
  const [formBase, setFormBase] = useState("")
  const [formKey, setFormKey] = useState("")
  const [createLoading, setCreateLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await modelApi.list()
      setProviders(res.items)
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
      await modelApi.create({
        name: formName.trim(),
        provider_type: formType.trim(),
        api_base: formBase.trim(),
        api_key: formKey.trim(),
      })
      setCreateOpen(false)
      setFormName("")
      setFormType("")
      setFormBase("")
      setFormKey("")
      load()
    } finally {
      setCreateLoading(false)
    }
  }

  async function handleTest(id: string) {
    setTestingId(id)
    try {
      const res = await modelApi.test(id)
      setTestResult((prev) => ({ ...prev, [id]: { ok: res.success, msg: res.message } }))
    } catch (err) {
      setTestResult((prev) => ({
        ...prev,
        [id]: { ok: false, msg: err instanceof Error ? err.message : "测试失败" },
      }))
    } finally {
      setTestingId(null)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    await modelApi.delete(deleteTarget)
    load()
  }

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">模型供应商</h2>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 size-4" />
          添加
        </Button>
      </div>

      <div className="space-y-3">
        {providers.map((p) => (
          <Card key={p.id} size="sm">
            <CardHeader>
              <div className="flex items-center gap-2">
                <CardTitle>{p.name}</CardTitle>
                <Badge variant="secondary">{p.provider_type}</Badge>
                <Badge variant={p.is_active ? "default" : "outline"}>
                  {p.is_active ? "启用" : "停用"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{p.api_base}</span>
                <span className="text-xs text-muted-foreground">
                  {p.models.length} 模型
                </span>
                <div className="ml-auto flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleTest(p.id)}
                    disabled={testingId === p.id}
                  >
                    {testingId === p.id ? (
                      <Loader2 className="mr-1 size-3.5 animate-spin" />
                    ) : (
                      <PlayCircle className="mr-1 size-3.5" />
                    )}
                    测试
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setDeleteTarget(p.id)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </div>
              {testResult[p.id] && (
                <div className="mt-2 flex items-center gap-1.5 text-xs">
                  {testResult[p.id].ok ? (
                    <CheckCircle2 className="size-3.5 text-green-500" />
                  ) : (
                    <XCircle className="size-3.5 text-red-500" />
                  )}
                  <span>{testResult[p.id].msg}</span>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog
        open={createOpen}
        onOpenChange={(v) => {
          setCreateOpen(v)
          if (!v) { setFormName(""); setFormType(""); setFormBase(""); setFormKey("") }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加模型供应商</DialogTitle>
            <DialogDescription>配置新的模型 API 供应商</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label>名称 *</Label>
              <Input value={formName} onChange={(e) => setFormName(e.target.value)} required />
            </div>
            <div className="flex flex-col gap-2">
              <Label>类型 *</Label>
              <Input value={formType} onChange={(e) => setFormType(e.target.value)} placeholder="openai / azure / local" required />
            </div>
            <div className="flex flex-col gap-2">
              <Label>API Base *</Label>
              <Input value={formBase} onChange={(e) => setFormBase(e.target.value)} placeholder="https://api.openai.com/v1" required />
            </div>
            <div className="flex flex-col gap-2">
              <Label>API Key *</Label>
              <Input type="password" value={formKey} onChange={(e) => setFormKey(e.target.value)} required />
            </div>
            <DialogFooter>
              <Button variant="outline" type="button" onClick={() => setCreateOpen(false)}>取消</Button>
              <Button type="submit" disabled={createLoading}>
                {createLoading ? "添加中..." : "添加"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除供应商"
        description="确认删除此模型供应商？使用该供应商的智能体将无法正常运行。"
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}
