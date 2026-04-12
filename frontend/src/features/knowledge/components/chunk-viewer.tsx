import { useCallback, useEffect, useState } from "react"
import { Edit3, Layers } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { EmptyState } from "@/components/shared/empty-state"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ChunkEditorDrawer } from "./chunk-editor-drawer"
import { knowledgeApi, type Chunk, type ChunkLevel } from "@/api/knowledge"

const levelColors: Record<ChunkLevel, string> = {
  title: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  section: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  paragraph: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  sentence: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200",
}

interface ChunkViewerProps {
  kbId: string
  docId: string
}

export function ChunkViewer({ kbId, docId }: ChunkViewerProps) {
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [editingChunk, setEditingChunk] = useState<Chunk | null>(null)

  const pageSize = 20

  const loadChunks = useCallback(async () => {
    setLoading(true)
    try {
      const res = await knowledgeApi.listChunks(kbId, docId, {
        page: String(page),
        page_size: String(pageSize),
      })
      setChunks(res.items)
      setTotal(res.total)
    } finally {
      setLoading(false)
    }
  }, [kbId, docId, page])

  useEffect(() => {
    loadChunks()
  }, [loadChunks])

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    if (selected.size === chunks.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(chunks.map((c) => c.id)))
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  if (loading) {
    return <LoadingSpinner className="py-16" />
  }

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
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Checkbox
            checked={selected.size === chunks.length}
            onCheckedChange={toggleAll}
          />
          <span className="text-sm text-muted-foreground">
            {selected.size > 0 ? `已选 ${selected.size} 个` : `共 ${total} 个分块`}
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {chunks.map((chunk) => (
          <div
            key={chunk.id}
            className="flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/50"
          >
            <Checkbox
              checked={selected.has(chunk.id)}
              onCheckedChange={() => toggleSelect(chunk.id)}
              className="mt-0.5"
            />
            <div className="min-w-0 flex-1">
              <p className="line-clamp-3 text-sm">{chunk.content}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Badge
                  variant="outline"
                  className={`border-transparent ${levelColors[chunk.level]}`}
                >
                  {chunk.level}
                </Badge>
                <span className="text-xs text-muted-foreground">{chunk.token_count} tokens</span>
                <span className="text-xs text-muted-foreground">
                  质量 {(chunk.quality_score * 100).toFixed(0)}%
                </span>
                {chunk.is_edited && (
                  <Badge variant="outline" className="text-xs">已编辑</Badge>
                )}
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setEditingChunk(chunk)}
            >
              <Edit3 className="size-3.5" />
            </Button>
          </div>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            上一页
          </Button>
          <span className="text-sm text-muted-foreground">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
          </Button>
        </div>
      )}

      <ChunkEditorDrawer
        kbId={kbId}
        chunk={editingChunk}
        open={editingChunk !== null}
        onOpenChange={(open) => { if (!open) setEditingChunk(null) }}
        onSaved={loadChunks}
      />
    </div>
  )
}
