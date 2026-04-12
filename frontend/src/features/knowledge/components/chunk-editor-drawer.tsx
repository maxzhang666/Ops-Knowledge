import { useEffect, useState } from "react"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { knowledgeApi, type Chunk } from "@/api/knowledge"

interface ChunkEditorDrawerProps {
  kbId: string
  chunk: Chunk | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4)
}

export function ChunkEditorDrawer({ kbId, chunk, open, onOpenChange, onSaved }: ChunkEditorDrawerProps) {
  const [content, setContent] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (chunk) setContent(chunk.content)
  }, [chunk])

  async function handleSave() {
    if (!chunk) return
    setSaving(true)
    try {
      await knowledgeApi.editChunk(kbId, chunk.id, { content })
      onSaved()
      onOpenChange(false)
    } finally {
      setSaving(false)
    }
  }

  const tokens = estimateTokens(content)
  const changed = chunk ? content !== chunk.content : false

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>编辑分块</SheetTitle>
          <SheetDescription>
            修改分块内容后保存，将自动重新计算向量
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-auto px-4">
          <Textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="min-h-[300px] font-mono text-sm"
            rows={15}
          />
          <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary">~{tokens} tokens</Badge>
            {changed && <span className="text-yellow-600">已修改</span>}
          </div>
        </div>

        <SheetFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!changed || saving} onClick={handleSave}>
            {saving ? "保存中..." : "保存"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
