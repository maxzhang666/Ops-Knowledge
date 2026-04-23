import { useEffect, useState } from "react"
import { BookTemplate, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { workflowApi } from "@/api/workflow"
import { useEditorStore } from "../store"

interface TemplateRow {
  id: string
  name: string
  description: string | null
  category: string
  is_builtin: boolean
}


export function SaveAsTemplateDialog() {
  const workflow = useEditorStore((s) => s.workflow)
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [category, setCategory] = useState("general")
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    if (!workflow || !name.trim()) return
    setSaving(true)
    try {
      await workflowApi.saveAsTemplate(workflow.id, {
        name: name.trim(),
        description: description.trim() || undefined,
        category: category.trim() || "general",
      })
      toast.success("已保存为模板")
      setOpen(false)
      setName(""); setDescription(""); setCategory("general")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <BookTemplate className="mr-1 size-3.5" /> 另存为模板
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>保存为模板</DialogTitle>
          <DialogDescription>
            从当前草稿（未发布时）或最近发布版本快照新模板
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-xs">名称</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div>
            <Label className="text-xs">分类</Label>
            <Input value={category} onChange={(e) => setCategory(e.target.value)} />
          </div>
          <div>
            <Label className="text-xs">描述（可选）</Label>
            <Textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>取消</Button>
          <Button onClick={handleSave} disabled={saving || !name.trim()}>
            {saving ? "保存中..." : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


interface CreateFromTemplateProps {
  onCreated?: (workflowId: string) => void
  triggerLabel?: string
}

export function CreateFromTemplateDialog({
  onCreated,
  triggerLabel = "从模板创建",
}: CreateFromTemplateProps) {
  const [open, setOpen] = useState(false)
  const [templates, setTemplates] = useState<TemplateRow[]>([])
  const [loading, setLoading] = useState(false)
  const [pickedId, setPickedId] = useState<string | null>(null)
  const [wfName, setWfName] = useState("")
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    workflowApi.listTemplates()
      .then((rows) => setTemplates(rows))
      .finally(() => setLoading(false))
  }, [open])

  async function handleCreate() {
    if (!pickedId || !wfName.trim()) return
    setCreating(true)
    try {
      const res = await workflowApi.createFromTemplate(pickedId, wfName.trim())
      toast.success("已基于模板创建草稿")
      setOpen(false)
      setPickedId(null); setWfName("")
      onCreated?.(res.id)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "创建失败")
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(tplId: string) {
    if (!window.confirm("确定删除此模板？")) return
    try {
      await workflowApi.deleteTemplate(tplId)
      setTemplates((xs) => xs.filter((t) => t.id !== tplId))
      toast.success("已删除模板")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败")
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <Plus className="mr-1 size-3.5" /> {triggerLabel}
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>选择模板</DialogTitle>
          <DialogDescription>从已保存模板创建一个新的草稿工作流</DialogDescription>
        </DialogHeader>
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {loading && <p className="text-xs text-muted-foreground">加载中...</p>}
          {!loading && templates.length === 0 && (
            <p className="text-xs text-muted-foreground">暂无模板</p>
          )}
          {templates.map((t) => (
            <div
              key={t.id}
              className={`flex items-start justify-between gap-2 rounded-md border p-2 text-xs ${
                pickedId === t.id ? "border-primary bg-primary/5" : ""
              }`}
            >
              <button
                type="button"
                onClick={() => setPickedId(t.id)}
                className="min-w-0 flex-1 text-left"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium">{t.name}</span>
                  <span className="rounded bg-muted px-1 text-[10px]">{t.category}</span>
                  {t.is_builtin && (
                    <span className="rounded bg-blue-100 px-1 text-[10px] text-blue-900">内置</span>
                  )}
                </div>
                {t.description && (
                  <div className="mt-0.5 text-muted-foreground">{t.description}</div>
                )}
              </button>
              {!t.is_builtin && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 shrink-0"
                  onClick={() => handleDelete(t.id)}
                >
                  <Trash2 className="size-3 text-destructive" />
                </Button>
              )}
            </div>
          ))}
        </div>
        {pickedId && (
          <div className="space-y-1">
            <Label className="text-xs">新工作流名称</Label>
            <Input
              value={wfName}
              onChange={(e) => setWfName(e.target.value)}
              placeholder="例：订单问答 Workflow"
            />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>取消</Button>
          <Button
            onClick={handleCreate}
            disabled={!pickedId || !wfName.trim() || creating}
          >
            {creating ? "创建中..." : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
