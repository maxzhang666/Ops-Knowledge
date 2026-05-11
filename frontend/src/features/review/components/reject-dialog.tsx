import { useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"

export function RejectDialog({
  open,
  onOpenChange,
  unitTitle,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  unitTitle: string
  onConfirm: (comment: string) => Promise<void>
}) {
  const [comment, setComment] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function submit() {
    if (!comment.trim()) return
    setSubmitting(true)
    try {
      await onConfirm(comment.trim())
      setComment("")
      onOpenChange(false)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>驳回「{unitTitle}」</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">驳回必须填写理由，便于作者修改后重新提交。</p>
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="说明驳回理由..."
            rows={4}
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={submit}
            disabled={submitting || !comment.trim()}
          >
            {submitting ? "提交中..." : "确认驳回"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
