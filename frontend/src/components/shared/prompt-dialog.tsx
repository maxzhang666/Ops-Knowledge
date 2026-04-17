import { useEffect, useRef, useState } from "react"
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

interface PromptDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  label?: string
  placeholder?: string
  defaultValue?: string
  confirmText?: string
  validate?: (value: string) => string | null  // returns error msg or null
  onConfirm: (value: string) => void | Promise<void>
}

/**
 * Single-field text input dialog — replaces window.prompt with a themed
 * component. Auto-focuses the input and submits on Enter.
 */
export function PromptDialog({
  open,
  onOpenChange,
  title,
  description,
  label,
  placeholder,
  defaultValue = "",
  confirmText = "确认",
  validate,
  onConfirm,
}: PromptDialogProps) {
  const [value, setValue] = useState(defaultValue)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setValue(defaultValue)
      setError(null)
      // Autofocus slightly after mount so the dialog animation doesn't steal focus back
      setTimeout(() => inputRef.current?.select(), 30)
    }
  }, [open, defaultValue])

  async function handleConfirm() {
    const trimmed = value.trim()
    if (validate) {
      const err = validate(trimmed)
      if (err) { setError(err); return }
    }
    if (!trimmed) { setError("不能为空"); return }
    setLoading(true)
    try {
      await onConfirm(trimmed)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败")
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault()
      handleConfirm()
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <div className="flex flex-col gap-1.5 py-2">
          {label && <label className="text-sm font-medium">{label}</label>}
          <Input
            ref={inputRef}
            value={value}
            placeholder={placeholder}
            onChange={(e) => { setValue(e.target.value); if (error) setError(null) }}
            onKeyDown={handleKeyDown}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button disabled={loading} onClick={handleConfirm}>
            {loading ? "处理中..." : confirmText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
