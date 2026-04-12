import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { knowledgeApi } from "@/api/knowledge"

interface KBCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}

export function KBCreateDialog({ open, onOpenChange, onCreated }: KBCreateDialogProps) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [shareToDept, setShareToDept] = useState(true)
  const [loading, setLoading] = useState(false)

  function reset() {
    setName("")
    setDescription("")
    setShareToDept(true)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return

    setLoading(true)
    try {
      await knowledgeApi.createKB({
        name: name.trim(),
        description: description.trim() || undefined,
        share_to_dept: shareToDept,
      })
      reset()
      onOpenChange(false)
      onCreated()
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v)
        if (!v) reset()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>创建知识库</DialogTitle>
          <DialogDescription>创建一个新的知识库来管理文档和知识</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="kb-name">名称 *</Label>
            <Input
              id="kb-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="输入知识库名称"
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="kb-desc">描述</Label>
            <Textarea
              id="kb-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="可选描述"
              rows={3}
            />
          </div>
          <div className="flex items-center gap-2">
            <Checkbox
              id="kb-share"
              checked={shareToDept}
              onCheckedChange={(v) => setShareToDept(v as boolean)}
            />
            <Label htmlFor="kb-share">共享至部门</Label>
          </div>
          <DialogFooter>
            <Button variant="outline" type="button" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" disabled={!name.trim() || loading}>
              {loading ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
