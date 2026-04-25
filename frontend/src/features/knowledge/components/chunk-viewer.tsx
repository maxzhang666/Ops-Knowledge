import { useCallback, useEffect, useMemo, useState } from "react"
import { Edit3, Layers, Scissors, Trash2, Save, X, PencilLine } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Textarea } from "@/components/ui/textarea"
import { EmptyState } from "@/components/shared/empty-state"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { cn } from "@/lib/utils"
import { ChunkSplitInteractive } from "./chunk-split-interactive"
import { knowledgeApi, type Chunk } from "@/api/knowledge"

const levelColors: Record<number, string> = {
  0: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  1: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  2: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  3: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200",
}

const levelLabels: Record<number, string> = {
  0: "L0", 1: "L1", 2: "L2", 3: "L3",
}

type RightMode = "view" | "edit" | "split"

interface ChunkViewerProps {
  kbId: string
  docId: string
}

/**
 * Two-pane chunk viewer: left list + right content/edit area.
 * Supports inline edit, interactive split, single/batch delete, batch merge.
 */
export function ChunkViewer({ kbId, docId }: ChunkViewerProps) {
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [activeId, setActiveId] = useState<string | null>(null)
  const [mode, setMode] = useState<RightMode>("view")
  const [editContent, setEditContent] = useState("")
  const [editTags, setEditTags] = useState("")
  const [editNotes, setEditNotes] = useState("")

  const [confirmDelete, setConfirmDelete] = useState<"single" | "batch" | null>(null)
  const pageSize = 20

  const loadChunks = useCallback(async () => {
    setLoading(true)
    try {
      const res = await knowledgeApi.listChunks(kbId, {
        document_id: docId,
        page: String(page),
        page_size: String(pageSize),
      })
      setChunks(res.items)
      setTotal(res.total)
    } finally {
      setLoading(false)
    }
  }, [kbId, docId, page])

  useEffect(() => { loadChunks() }, [loadChunks])

  // Keep activeId valid after reload
  useEffect(() => {
    if (activeId && !chunks.some((c) => c.id === activeId)) {
      setActiveId(null)
      setMode("view")
    }
  }, [chunks, activeId])

  const activeChunk = useMemo(
    () => chunks.find((c) => c.id === activeId) ?? null,
    [chunks, activeId],
  )

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function clearSelection() { setSelected(new Set()) }

  function pickChunk(c: Chunk) {
    setActiveId(c.id)
    setMode("view")
  }

  function enterEdit() {
    if (!activeChunk) return
    setEditContent(activeChunk.content)
    const meta = (activeChunk.metadata ?? {}) as Record<string, unknown>
    const tags = Array.isArray(meta.tags) ? (meta.tags as string[]).join(", ") : ""
    setEditTags(tags)
    setEditNotes(typeof meta.notes === "string" ? meta.notes : "")
    setMode("edit")
  }

  async function saveEdit() {
    if (!activeChunk) return
    try {
      // Save content first (may trigger re-embedding on the backend)
      if (editContent !== activeChunk.content) {
        await knowledgeApi.editChunk(kbId, activeChunk.id, { content: editContent })
      }
      // Then tags/notes (separate endpoint, purely metadata)
      const origMeta = (activeChunk.metadata ?? {}) as Record<string, unknown>
      const origTags = Array.isArray(origMeta.tags) ? (origMeta.tags as string[]).join(", ") : ""
      const origNotes = typeof origMeta.notes === "string" ? origMeta.notes : ""
      if (editTags !== origTags || editNotes !== origNotes) {
        const tagsArr = editTags.split(",").map((t) => t.trim()).filter(Boolean)
        await knowledgeApi.annotateChunk(kbId, activeChunk.id, {
          tags: tagsArr,
          notes: editNotes || null,
        })
      }
      toast.success("已保存")
      setMode("view")
      loadChunks()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败")
    }
  }

  async function doDeleteSingle() {
    if (!activeChunk) return
    try {
      await knowledgeApi.deleteChunk(kbId, activeChunk.id)
      toast.success("已删除")
      setActiveId(null); setMode("view")
      loadChunks()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  async function doBatchDelete() {
    const ids = Array.from(selected)
    try {
      await Promise.all(ids.map((id) => knowledgeApi.deleteChunk(kbId, id)))
      toast.success(`已删除 ${ids.length} 项`)
      clearSelection()
      loadChunks()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "部分删除失败")
    }
  }

  // Batch merge: require adjacency (contiguous positions in current page)
  const batchAdjacent = useMemo(() => {
    if (selected.size < 2) return false
    const picked = chunks.filter((c) => selected.has(c.id)).sort((a, b) => a.position - b.position)
    for (let i = 1; i < picked.length; i++) {
      if (picked[i].position !== picked[i - 1].position + 1) return false
    }
    return true
  }, [chunks, selected])

  async function doBatchMerge() {
    if (!batchAdjacent) return
    const ids = chunks
      .filter((c) => selected.has(c.id))
      .sort((a, b) => a.position - b.position)
      .map((c) => c.id)
    try {
      await knowledgeApi.mergeChunks(kbId, { chunk_ids: ids })
      toast.success(`已合并 ${ids.length} 项`)
      clearSelection()
      loadChunks()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "合并失败")
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  if (loading) return <LoadingSpinner className="py-16" />

  if (chunks.length === 0) {
    return (
      <EmptyState
        icon={<Layers className="h-10 w-10" />}
        title="暂无分块"
        description="文档处理完成后将显示分块列表"
      />
    )
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Left pane — chunk list */}
      <div className="flex w-80 shrink-0 flex-col border-r">
        <div className="flex items-center justify-between border-b px-3 py-2 text-xs text-muted-foreground">
          <span>共 {total} 个分块</span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                ‹
              </Button>
              <span>{page}/{totalPages}</span>
              <Button variant="ghost" size="icon-sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                ›
              </Button>
            </div>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {chunks.map((chunk) => {
            const isActive = chunk.id === activeId
            const isPicked = selected.has(chunk.id)
            return (
              <div
                key={chunk.id}
                className={cn(
                  "group mb-1 flex cursor-pointer items-start gap-2 rounded-md border px-2 py-1.5 text-xs transition-colors hover:bg-muted",
                  isActive && "border-primary bg-muted",
                )}
                onClick={() => pickChunk(chunk)}
              >
                <Checkbox
                  checked={isPicked}
                  onCheckedChange={() => toggleSelect(chunk.id)}
                  onClick={(e) => e.stopPropagation()}
                  className="mt-0.5"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <Badge
                      variant="outline"
                      className={cn("border-transparent", levelColors[chunk.level] ?? levelColors[3])}
                    >
                      {levelLabels[chunk.level] ?? `L${chunk.level}`}
                    </Badge>
                    <span>{chunk.token_count}t</span>
                    {chunk.quality_score != null && (
                      <span className="text-muted-foreground">{(chunk.quality_score * 100).toFixed(0)}%</span>
                    )}
                    <span className="text-muted-foreground">命中 {chunk.hit_count}</span>
                    {chunk.is_manually_edited && (
                      <PencilLine className="size-3 text-amber-500" />
                    )}
                  </div>
                  <p className="mt-1 line-clamp-2 text-muted-foreground">{chunk.content}</p>
                </div>
              </div>
            )
          })}
        </div>

        {/* Batch toolbar */}
        {selected.size > 0 && (
          <div className="flex items-center justify-between border-t bg-muted/50 px-3 py-2 text-xs">
            <span>已选 {selected.size}</span>
            <div className="flex gap-1">
              <Button
                size="sm"
                variant="outline"
                disabled={!batchAdjacent}
                title={batchAdjacent ? "合并相邻切片" : "所选切片不相邻，无法合并"}
                onClick={doBatchMerge}
              >
                合并
              </Button>
              <Button size="sm" variant="outline" onClick={() => setConfirmDelete("batch")}>
                删除
              </Button>
              <Button size="sm" variant="ghost" onClick={clearSelection}>
                <X className="size-3.5" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Right pane — content / edit / split */}
      <div className="min-w-0 flex-1">
        {!activeChunk ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            从左侧选择切片
          </div>
        ) : mode === "split" ? (
          <ChunkSplitInteractive
            kbId={kbId}
            chunk={activeChunk}
            onCancel={() => setMode("view")}
            onDone={() => { setMode("view"); loadChunks() }}
          />
        ) : (
          <div className="flex h-full min-h-0 flex-col">
            <div className="flex items-center justify-between border-b px-4 py-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className={cn("border-transparent", levelColors[activeChunk.level])}>
                  {levelLabels[activeChunk.level] ?? `L${activeChunk.level}`}
                </Badge>
                <span>{activeChunk.token_count} tokens</span>
                {activeChunk.quality_score != null && (
                  <span>质量 {(activeChunk.quality_score * 100).toFixed(0)}%</span>
                )}
                <span>命中 {activeChunk.hit_count}</span>
              </div>
              <div className="flex items-center gap-1">
                {mode === "view" && (
                  <>
                    <Button size="sm" variant="outline" onClick={enterEdit}>
                      <Edit3 className="mr-1 size-3.5" /> 编辑
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setMode("split")}>
                      <Scissors className="mr-1 size-3.5" /> 拆分
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmDelete("single")}>
                      <Trash2 className="mr-1 size-3.5" /> 删除
                    </Button>
                  </>
                )}
                {mode === "edit" && (
                  <>
                    <Button size="sm" variant="outline" onClick={() => setMode("view")}>取消</Button>
                    <Button size="sm" onClick={saveEdit}>
                      <Save className="mr-1 size-3.5" /> 保存
                    </Button>
                  </>
                )}
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {mode === "view" ? (
                <>
                  <pre className="whitespace-pre-wrap text-sm leading-relaxed">{activeChunk.content}</pre>
                  {(() => {
                    const meta = (activeChunk.metadata ?? {}) as Record<string, unknown>
                    const tags = Array.isArray(meta.tags) ? (meta.tags as string[]) : []
                    const notes = typeof meta.notes === "string" ? meta.notes : ""
                    const keywords = Array.isArray(meta.keywords) ? (meta.keywords as string[]) : []
                    const questions = Array.isArray(meta.questions) ? (meta.questions as string[]) : []
                    const raptorChildren = Array.isArray(meta.raptor_children)
                      ? (meta.raptor_children as string[])
                      : []
                    if (tags.length === 0 && !notes && keywords.length === 0 && questions.length === 0 && raptorChildren.length === 0) return null
                    return (
                      <div className="mt-4 flex flex-col gap-2 border-t pt-3 text-xs text-muted-foreground">
                        {raptorChildren.length > 0 && (
                          <div className="flex items-start gap-2">
                            <span className="shrink-0">RAPTOR 摘要 · 覆盖 {raptorChildren.length} 个子切片</span>
                          </div>
                        )}
                        {keywords.length > 0 && (
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span>关键词：</span>
                            {keywords.map((k) => (
                              <Badge key={k} variant="outline" className="text-[10px]">{k}</Badge>
                            ))}
                          </div>
                        )}
                        {questions.length > 0 && (
                          <div className="flex flex-col gap-0.5">
                            <span>问题：</span>
                            {questions.map((q, i) => (
                              <span key={i} className="pl-3">• {q}</span>
                            ))}
                          </div>
                        )}
                        {tags.length > 0 && (
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span>标签：</span>
                            {tags.map((t) => (
                              <Badge key={t} variant="secondary" className="text-[10px]">{t}</Badge>
                            ))}
                          </div>
                        )}
                        {notes && (
                          <div>
                            <span>笔记：</span>
                            <span className="whitespace-pre-wrap">{notes}</span>
                          </div>
                        )}
                      </div>
                    )
                  })()}
                </>
              ) : (
                <div className="flex h-full flex-col gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-muted-foreground">内容</label>
                    <Textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      className="min-h-[200px] flex-1 font-mono text-sm"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-muted-foreground">
                      标签 <span className="font-normal">（逗号分隔）</span>
                    </label>
                    <input
                      type="text"
                      value={editTags}
                      onChange={(e) => setEditTags(e.target.value)}
                      className="h-9 rounded-md border bg-background px-3 text-sm"
                      placeholder="例如：故障排查, 常见问题"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-muted-foreground">笔记</label>
                    <Textarea
                      value={editNotes}
                      onChange={(e) => setEditNotes(e.target.value)}
                      className="min-h-[80px] text-sm"
                      placeholder="对这个切片的补充说明（不会参与向量检索）"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete === "single"}
        onOpenChange={(v) => { if (!v) setConfirmDelete(null) }}
        title="删除切片"
        description="确认删除此切片？此操作不可撤销。"
        confirmText="删除"
        destructive
        onConfirm={doDeleteSingle}
      />
      <ConfirmDialog
        open={confirmDelete === "batch"}
        onOpenChange={(v) => { if (!v) setConfirmDelete(null) }}
        title={`批量删除 ${selected.size} 项`}
        description="确认删除所选切片？此操作不可撤销。"
        confirmText="删除"
        destructive
        onConfirm={doBatchDelete}
      />
    </div>
  )
}
