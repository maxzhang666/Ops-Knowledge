import { useState } from "react"
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

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmText?: string
  typeToConfirm?: string
  destructive?: boolean
  onConfirm: () => void | Promise<void>
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmText = "确认",
  typeToConfirm,
  destructive,
  onConfirm,
}: ConfirmDialogProps) {
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)

  const canConfirm = typeToConfirm ? input === typeToConfirm : true

  async function handleConfirm() {
    setLoading(true)
    try {
      await onConfirm()
      onOpenChange(false)
    } finally {
      setLoading(false)
      setInput("")
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setInput("") }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {typeToConfirm && (
          <div className="py-2">
            <p className="mb-2 text-sm text-muted-foreground">
              请输入 <span className="font-mono font-semibold">{typeToConfirm}</span> 以确认
            </p>
            <Input value={input} onChange={(e) => setInput(e.target.value)} />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            disabled={!canConfirm || loading}
            onClick={handleConfirm}
          >
            {loading ? "处理中..." : confirmText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
