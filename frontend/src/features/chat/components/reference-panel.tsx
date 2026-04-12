import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import type { RetrievalChunk } from "@/api/chat"

interface ReferencePanelProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  chunks: RetrievalChunk[]
  highlightIndex?: number
}

export function ReferencePanel({ open, onOpenChange, chunks, highlightIndex }: ReferencePanelProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>引用来源</SheetTitle>
          <SheetDescription>检索到 {chunks.length} 个相关片段</SheetDescription>
        </SheetHeader>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {chunks.map((chunk, i) => (
            <div
              key={chunk.chunk_id}
              className={`rounded-lg border p-3 text-sm ${highlightIndex === i + 1 ? "border-primary bg-primary/5" : ""}`}
            >
              <div className="mb-2 flex items-center gap-2">
                <Badge variant="secondary" className="text-[10px]">[{i + 1}]</Badge>
                <span className="truncate font-medium">{chunk.document_name}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {(chunk.score * 100).toFixed(1)}%
                </span>
              </div>
              <p className="line-clamp-4 text-muted-foreground">{chunk.content}</p>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}
