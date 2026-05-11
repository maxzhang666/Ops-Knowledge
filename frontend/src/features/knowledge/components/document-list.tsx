import { useCallback, useEffect, useMemo, useState } from "react"
import { FileText, Clock, CheckCircle2, XCircle, Trash2, RefreshCcw, X, FolderInput } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { EmptyState } from "@/components/shared/empty-state"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TimeDisplay } from "@/components/shared/time-display"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { DocumentStatusBadge } from "./document-status-badge"
import { DocumentUpload } from "./document-upload"
import { cn } from "@/lib/utils"
import { knowledgeApi, type Document, type DocumentStatus, type Folder } from "@/api/knowledge"
import { useKnowledgeStore } from "@/stores/knowledge"

function StatusIcon({ status }: { status: DocumentStatus }) {
  switch (status) {
    case "pending":
      return <Clock className="size-3.5 shrink-0 text-amber-500" />
    case "processing":
      return <Clock className="size-3.5 shrink-0 animate-pulse text-amber-500" />
    case "completed":
      return <CheckCircle2 className="size-3.5 shrink-0 text-green-500" />
    case "error":
      return <XCircle className="size-3.5 shrink-0 text-red-500" />
  }
}

// File icon tints by source type — replaces the right-side type badge so
// the title row gets back the ~80px of horizontal space the badge ate.
const typeIconColors: Record<string, string> = {
  pdf: "text-red-500",
  word: "text-blue-500",
  txt: "text-gray-500",
  markdown: "text-purple-500",
  html: "text-orange-500",
  csv: "text-green-500",
  api_ingestion: "text-cyan-500",
  qa_pair: "text-indigo-500",
}

// Short uppercase labels shown inline in the meta row.
const typeLabels: Record<string, string> = {
  pdf: "PDF",
  word: "WORD",
  txt: "TXT",
  markdown: "MD",
  html: "HTML",
  csv: "CSV",
  api_ingestion: "API",
  qa_pair: "QA",
}

interface DocumentListProps {
  kbId: string
  refreshToken?: number
  onDocumentsChanged?: () => void
}

export function DocumentList({ kbId, refreshToken, onDocumentsChanged }: DocumentListProps) {
  const { selectedFolderId, selectedDocId, setSelectedDoc } = useKnowledgeStore()
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [moveOpen, setMoveOpen] = useState(false)
  const [moveTargetFolderId, setMoveTargetFolderId] = useState<string>("__root__")
  const [folders, setFolders] = useState<Folder[]>([])

  const loadDocs = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {}
      if (selectedFolderId) params.folder_id = selectedFolderId
      const res = await knowledgeApi.listDocuments(kbId, params)
      setDocs(res.items)
      // Prune selection of missing docs (after delete, reload, etc.)
      setPicked((prev) => {
        const ids = new Set(res.items.map((d) => d.id))
        const next = new Set<string>()
        prev.forEach((id) => { if (ids.has(id)) next.add(id) })
        return next
      })
    } finally {
      setLoading(false)
    }
  }, [kbId, selectedFolderId])

  useEffect(() => { loadDocs() }, [loadDocs, refreshToken])

  // Clear selection on folder change — different scope
  useEffect(() => { setPicked(new Set()) }, [selectedFolderId])

  const hasActive = useMemo(
    () => docs.some((d) => d.status === "pending" || d.status === "processing"),
    [docs],
  )
  useEffect(() => {
    if (!hasActive) return
    const id = setInterval(loadDocs, 5000)
    return () => clearInterval(id)
  }, [hasActive, loadDocs])

  function toggle(id: string) {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    if (picked.size === docs.length) setPicked(new Set())
    else setPicked(new Set(docs.map((d) => d.id)))
  }

  async function handleBatchDelete() {
    const ids = Array.from(picked)
    if (ids.length === 0) return
    try {
      await knowledgeApi.batchDeleteDocuments(kbId, { ids })
      toast.success(`已删除 ${ids.length} 个文档`)
      setPicked(new Set())
      loadDocs()
      onDocumentsChanged?.()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "批量删除失败")
    }
  }

  async function handleBatchReprocess() {
    const ids = Array.from(picked)
    if (ids.length === 0) return
    try {
      await knowledgeApi.batchReprocessDocuments(kbId, { ids })
      toast.success(`已重新处理 ${ids.length} 个文档`)
      setPicked(new Set())
      loadDocs()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "重新处理失败")
    }
  }

  async function openMoveDialog() {
    try {
      const fs = await knowledgeApi.listFolders(kbId)
      setFolders(fs)
      setMoveTargetFolderId("__root__")
      setMoveOpen(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "加载文件夹列表失败")
    }
  }

  async function handleBatchMove() {
    const ids = Array.from(picked)
    if (ids.length === 0) return
    const target = moveTargetFolderId === "__root__" ? null : moveTargetFolderId
    try {
      await knowledgeApi.batchMoveDocuments(kbId, { ids, target_folder_id: target })
      toast.success(`已移动 ${ids.length} 个文档`)
      setMoveOpen(false)
      setPicked(new Set())
      loadDocs()
      onDocumentsChanged?.()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "移动失败")
    }
  }

  if (loading) return <LoadingSpinner className="py-16" />

  const selectMode = picked.size > 0

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        {selectMode ? (
          <div className="flex items-center gap-1.5">
            <Checkbox
              checked={picked.size === docs.length && docs.length > 0}
              onCheckedChange={toggleAll}
            />
            <span className="text-sm text-muted-foreground">已选 {picked.size}</span>
          </div>
        ) : (
          <h3 className="text-sm font-medium text-muted-foreground">
            {docs.length} 个文档
          </h3>
        )}
        <DocumentUpload
          kbId={kbId}
          folderId={selectedFolderId}
          onUploaded={() => { loadDocs(); onDocumentsChanged?.() }}
        />
      </div>

      {docs.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-10 w-10" />}
          title="暂无文档"
          description="上传文档以开始构建知识库"
        />
      ) : (
        <div className="flex flex-col gap-1">
          {docs.map((doc) => {
            const isPicked = picked.has(doc.id)
            return (
              <div
                key={doc.id}
                title={doc.title}
                className={cn(
                  "group flex items-center gap-2 rounded-md border px-2.5 py-2 cursor-pointer transition-colors hover:bg-muted",
                  selectedDocId === doc.id && "border-primary bg-muted",
                  isPicked && "border-primary/60 bg-primary/5",
                )}
                onClick={() => setSelectedDoc(doc.id)}
              >
                <Checkbox
                  checked={isPicked}
                  onCheckedChange={() => toggle(doc.id)}
                  onClick={(e) => e.stopPropagation()}
                  className={cn(
                    "shrink-0 transition-opacity",
                    !selectMode && "opacity-0 group-hover:opacity-100 data-[state=checked]:opacity-100",
                  )}
                />
                <FileText
                  className={cn(
                    "size-4 shrink-0",
                    typeIconColors[doc.source_type] ?? "text-muted-foreground",
                  )}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <StatusIcon status={doc.status} />
                    <p className="truncate text-sm font-medium">{doc.title}</p>
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    <span className="font-medium">{typeLabels[doc.source_type] ?? doc.source_type}</span>
                    <span className="mx-1.5">·</span>
                    {doc.chunk_count} 分块
                    <span className="mx-1.5">·</span>
                    <TimeDisplay value={doc.created_at} />
                  </p>
                </div>
                <DocumentStatusBadge status={doc.status} className="shrink-0" />
              </div>
            )
          })}
        </div>
      )}

      {/* Batch action bar — floats at bottom when any doc is picked */}
      {selectMode && (
        <div className="sticky bottom-0 -mx-3 -mb-3 flex items-center justify-between gap-2 border-t bg-background/95 px-3 py-2 backdrop-blur">
          <span className="text-xs text-muted-foreground">已选 {picked.size} 项</span>
          <div className="flex gap-1">
            <Button size="sm" variant="outline" onClick={openMoveDialog}>
              <FolderInput className="mr-1 size-3.5" /> 移动
            </Button>
            <Button size="sm" variant="outline" onClick={handleBatchReprocess}>
              <RefreshCcw className="mr-1 size-3.5" /> 重新处理
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="mr-1 size-3.5" /> 删除
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>
              <X className="size-3.5" />
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`删除 ${picked.size} 个文档`}
        description="所选文档及其切片、向量数据都将被删除。此操作不可撤销。"
        confirmText="删除"
        destructive
        onConfirm={handleBatchDelete}
      />

      <Dialog open={moveOpen} onOpenChange={setMoveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>移动 {picked.size} 个文档</DialogTitle>
            <DialogDescription>
              选择目标文件夹。移动后文档仍保留所有切片和向量数据，不会触发重新处理。
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2 py-2">
            <Label>目标文件夹</Label>
            <Select value={moveTargetFolderId} onValueChange={(v) => v && setMoveTargetFolderId(v)}>
              <SelectTrigger className="w-full">
                {moveTargetFolderId === "__root__"
                  ? <span>根目录（无文件夹）</span>
                  : <span className="truncate">{flattenFolders(folders).find((f) => f.id === moveTargetFolderId)?.name ?? "(未选)"}</span>}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__root__">根目录（无文件夹）</SelectItem>
                {flattenFolders(folders).map((f) => (
                  <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMoveOpen(false)}>取消</Button>
            <Button onClick={handleBatchMove}>移动</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// Flatten the folder tree into a depth-prefixed list for the Select.
function flattenFolders(
  nodes: Folder[], depth = 0, out: Array<Folder & { depth: number }> = [],
): Array<Folder & { depth: number }> {
  for (const n of nodes) {
    out.push({ ...n, depth, name: `${"　".repeat(depth)}${n.name}` })
    if (n.children?.length) flattenFolders(n.children, depth + 1, out)
  }
  return out
}
