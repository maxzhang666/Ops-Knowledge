import { useState } from "react"
import { Eye, X } from "lucide-react"

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { DocumentPreview } from "@/features/knowledge/components/document-preview"
import { knowledgeApi } from "@/api/knowledge"
import type { RetrievalChunk } from "@/api/chat"

interface ReferencePanelProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  chunks: RetrievalChunk[]
  highlightIndex?: number
}

interface PreviewState {
  kbId: string
  docId: string
  sourceType: string
  title: string
  highlight: string
}

export function ReferencePanel({ open, onOpenChange, chunks, highlightIndex }: ReferencePanelProps) {
  const [preview, setPreview] = useState<PreviewState | null>(null)

  async function openOriginal(chunk: RetrievalChunk) {
    if (!chunk.document_id || !chunk.source_kb_id) return
    try {
      const doc = await knowledgeApi.getDocument(chunk.source_kb_id, chunk.document_id)
      setPreview({
        kbId: chunk.source_kb_id,
        docId: chunk.document_id,
        sourceType: doc.source_type,
        title: doc.title,
        highlight: chunk.content_preview,
      })
    } catch {
      // 失败静默 —— 用户仍可以看 chunk preview
    }
  }

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right">
          <SheetHeader>
            <SheetTitle>引用来源</SheetTitle>
            <SheetDescription>检索到 {chunks.length} 个相关片段</SheetDescription>
          </SheetHeader>
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {chunks.map((chunk, i) => (
              <div
                key={chunk.id}
                className={`rounded-lg border p-3 text-sm ${highlightIndex === i + 1 ? "border-primary bg-primary/5" : ""}`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <Badge variant="secondary" className="text-[10px]">[{i + 1}]</Badge>
                  <span className="truncate font-medium">{chunk.document_title}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {(chunk.score * 100).toFixed(1)}%
                  </span>
                </div>
                <p className="line-clamp-4 text-muted-foreground">{chunk.content_preview}</p>
                {chunk.document_id && chunk.source_kb_id && (
                  <div className="mt-2">
                    <Button
                      variant="ghost" size="sm"
                      className="h-6 px-2 text-[11px]"
                      onClick={() => openOriginal(chunk)}
                    >
                      <Eye className="mr-1 size-3" /> 查看原文
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </SheetContent>
      </Sheet>

      {/* Plan 32 — 原文预览抽屉。PDF 走 PdfPreview，其他类型沿用 DocumentPreview */}
      <Sheet open={!!preview} onOpenChange={(v) => { if (!v) setPreview(null) }}>
        <SheetContent side="right" className="w-[min(900px,90vw)] sm:max-w-none p-0">
          <SheetHeader className="border-b px-4 py-2.5">
            <div className="flex items-center justify-between">
              <SheetTitle className="text-sm">{preview?.title ?? "原文预览"}</SheetTitle>
              <Button variant="ghost" size="icon-sm" onClick={() => setPreview(null)}>
                <X className="size-3.5" />
              </Button>
            </div>
            <SheetDescription className="text-xs">
              已自动定位并高亮检索片段
            </SheetDescription>
          </SheetHeader>
          {preview && (
            <div className="h-[calc(100vh-100px)]">
              <DocumentPreview
                kbId={preview.kbId}
                docId={preview.docId}
                sourceType={preview.sourceType}
                title={preview.title}
                highlightText={preview.highlight}
              />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  )
}
