import { useCallback, useEffect, useState } from "react"
import { Download, Move, RefreshCcw, Trash2, Archive } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TimeDisplay } from "@/components/shared/time-display"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { DocumentStatusBadge } from "./document-status-badge"
import { ProcessingProgress } from "./processing-progress"
import { ChunkViewer } from "./chunk-viewer"
import { DocumentPreview } from "./document-preview"

const PREVIEWABLE_TYPES = new Set(["markdown", "txt", "csv"])
import { knowledgeApi, type Document } from "@/api/knowledge"

interface DocumentDetailPanelProps {
  kbId: string
  docId: string
  onChanged: () => void
  onClosed: () => void
}

/**
 * Right column of the Documents tab. Shows a metadata bar + chunk viewer
 * for the selected document. For in-flight processing, replaces the chunk
 * area with ProcessingProgress.
 */
export function DocumentDetailPanel({ kbId, docId, onChanged, onClosed }: DocumentDetailPanelProps) {
  const [doc, setDoc] = useState<Document | null>(null)
  const [initLoading, setInitLoading] = useState(true)
  const [confirmDelete, setConfirmDelete] = useState(false)

  // Silent reload — does NOT flip `initLoading`, so the view keeps rendering
  // the current doc + chunks while the refresh happens in the background.
  const reload = useCallback(async () => {
    const d = await knowledgeApi.getDocument(kbId, docId)
    setDoc(d)
  }, [kbId, docId])

  // Fresh load only when docId changes — this IS the moment to show a spinner.
  useEffect(() => {
    let cancelled = false
    setInitLoading(true)
    setDoc(null)
    knowledgeApi.getDocument(kbId, docId)
      .then((d) => { if (!cancelled) setDoc(d) })
      .finally(() => { if (!cancelled) setInitLoading(false) })
    return () => { cancelled = true }
  }, [kbId, docId])

  // Poll every 3s while processing — silent so the detail panel doesn't flicker
  useEffect(() => {
    if (!doc || (doc.status !== "pending" && doc.status !== "processing")) return
    const id = setInterval(reload, 3000)
    return () => clearInterval(id)
  }, [doc, reload])

  async function handleDelete() {
    await knowledgeApi.deleteDocument(kbId, docId)
    onChanged()
    onClosed()
  }

  async function handleReprocess() {
    await knowledgeApi.reprocessDocument(kbId, docId)
    await reload()
  }

  async function handleDownload() {
    const blob = await knowledgeApi.downloadDocument(kbId, docId)
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = doc?.title ?? "document"
    a.click()
    URL.revokeObjectURL(url)
  }

  if (initLoading || !doc) return <LoadingSpinner className="py-16" />

  const isProcessing = doc.status === "pending" || doc.status === "processing"

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Metadata bar */}
      <div className="flex items-center gap-2 border-b px-4 py-2.5">
        <h2 className="min-w-0 flex-1 truncate text-sm font-medium" title={doc.title}>
          {doc.title}
        </h2>
        <Badge variant="outline" className="uppercase">{doc.source_type}</Badge>
        <DocumentStatusBadge status={doc.status} />
        <span className="text-xs text-muted-foreground">
          {formatSize(doc.file_size)} · {doc.chunk_count} 分块 · <TimeDisplay value={doc.updated_at} />
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          <Button variant="ghost" size="icon-sm" title="下载" onClick={handleDownload}>
            <Download className="size-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" title="重新处理" onClick={handleReprocess}>
            <RefreshCcw className="size-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" title="移动" disabled>
            <Move className="size-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" title="归档" disabled>
            <Archive className="size-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" title="删除" onClick={() => setConfirmDelete(true)}>
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>

      {/* Body: progress for pending/processing; chunks + preview otherwise */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {isProcessing ? (
          <div className="p-6">
            <h3 className="mb-2 text-sm font-medium">处理进度</h3>
            {doc.processing_progress && <ProcessingProgress progress={doc.processing_progress} />}
            {doc.error_message && <p className="mt-2 text-xs text-red-600">{doc.error_message}</p>}
          </div>
        ) : doc.status === "error" ? (
          <div className="p-6">
            <p className="text-sm text-red-600">处理失败：{doc.error_message || "未知错误"}</p>
            <Button className="mt-3" variant="outline" size="sm" onClick={handleReprocess}>
              <RefreshCcw className="mr-1.5 size-3.5" /> 重新处理
            </Button>
          </div>
        ) : PREVIEWABLE_TYPES.has(doc.source_type.toLowerCase()) ? (
          <Tabs defaultValue="chunks" className="flex h-full min-h-0 flex-col">
            <TabsList className="mx-4 mt-2 self-start" variant="line">
              <TabsTrigger value="chunks">切片</TabsTrigger>
              <TabsTrigger value="preview">原文预览</TabsTrigger>
            </TabsList>
            <TabsContent value="chunks" className="min-h-0 flex-1 overflow-hidden">
              <ChunkViewer kbId={kbId} docId={docId} />
            </TabsContent>
            <TabsContent value="preview" className="min-h-0 flex-1 overflow-auto">
              <DocumentPreview
                kbId={kbId}
                docId={docId}
                sourceType={doc.source_type}
                title={doc.title}
              />
            </TabsContent>
          </Tabs>
        ) : (
          <ChunkViewer kbId={kbId} docId={docId} />
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="删除文档"
        description={`确认删除 "${doc.title}"？此操作不可撤销。`}
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)}GB`
}
