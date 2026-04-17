import { useMemo, useState } from "react"
import { Scissors } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { knowledgeApi, type Chunk, type ChunkSplitPreviewItem } from "@/api/knowledge"

interface ChunkSplitInteractiveProps {
  kbId: string
  chunk: Chunk
  onCancel: () => void
  onDone: () => void
}

/**
 * Interactive split editor (spec 08:72).
 *
 * User clicks inside the chunk content to place split points. Each split
 * point renders as a cyan vertical bar with a × to remove. The preview
 * pane below updates in real time with per-segment token estimates.
 *
 * Confirmation calls backend; backend owns the authoritative split.
 */
export function ChunkSplitInteractive({ kbId, chunk, onCancel, onDone }: ChunkSplitInteractiveProps) {
  // Positions are character offsets (0 < p < content.length), sorted ascending, unique.
  const [positions, setPositions] = useState<number[]>([])
  const [preview, setPreview] = useState<ChunkSplitPreviewItem[] | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [saving, setSaving] = useState(false)

  const content = chunk.content

  // Render content as alternating spans of text + split markers.
  const segments = useMemo(() => {
    if (positions.length === 0) return [{ start: 0, end: content.length }]
    const sorted = [...positions].sort((a, b) => a - b)
    const out: { start: number; end: number }[] = []
    let prev = 0
    for (const p of sorted) {
      out.push({ start: prev, end: p })
      prev = p
    }
    out.push({ start: prev, end: content.length })
    return out
  }, [positions, content])

  function handleTextClick(e: React.MouseEvent<HTMLElement>) {
    // Find char offset from the clicked target + selection range.
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return
    const range = sel.getRangeAt(0)
    // Only accept clicks that landed inside our container text
    const container = e.currentTarget
    if (!container.contains(range.startContainer)) return

    // Compute absolute char offset by summing preceding text nodes.
    let offset = 0
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
    while (walker.nextNode()) {
      const node = walker.currentNode as Text
      if (node === range.startContainer) {
        offset += range.startOffset
        break
      }
      offset += node.textContent?.length ?? 0
    }

    if (offset <= 0 || offset >= content.length) return
    setPositions((prev) => Array.from(new Set([...prev, offset])).sort((a, b) => a - b))
    setPreview(null)
  }

  function removePosition(p: number) {
    setPositions((prev) => prev.filter((x) => x !== p))
    setPreview(null)
  }

  function estimateTokens(t: string) {
    return Math.max(1, Math.ceil(t.length / 4))
  }

  async function refreshPreview() {
    if (positions.length === 0) { setPreview(null); return }
    setPreviewing(true)
    try {
      const res = await knowledgeApi.previewSplitChunk(kbId, chunk.id, {
        split_positions: positions,
      })
      setPreview(res.items)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "预览失败")
    } finally {
      setPreviewing(false)
    }
  }

  async function confirmSplit() {
    if (positions.length === 0) return
    setSaving(true)
    try {
      await knowledgeApi.splitChunk(kbId, chunk.id, { split_positions: positions })
      toast.success(`已拆分为 ${positions.length + 1} 块`)
      onDone()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "拆分失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Scissors className="size-3.5" />
          点击文本插入分割线（{positions.length} 个分割点，预览 {positions.length + 1} 个片段）
        </div>
        <div className="flex items-center gap-1">
          <Button size="sm" variant="outline" onClick={onCancel}>取消</Button>
          <Button
            size="sm"
            variant="outline"
            disabled={positions.length === 0 || previewing}
            onClick={refreshPreview}
          >
            {previewing ? "计算中..." : "预览"}
          </Button>
          <Button
            size="sm"
            disabled={positions.length === 0 || saving}
            onClick={confirmSplit}
          >
            {saving ? "拆分中..." : `确认拆分为 ${positions.length + 1} 块`}
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {/* Clickable content with split markers */}
        <div
          className="cursor-text whitespace-pre-wrap p-4 text-sm leading-relaxed"
          onClick={handleTextClick}
        >
          {segments.map((s, i) => (
            <span key={i}>
              {content.slice(s.start, s.end)}
              {i < segments.length - 1 && (
                <SplitMarker
                  position={segments[i + 1].start}
                  onRemove={removePosition}
                />
              )}
            </span>
          ))}
        </div>

        {/* Preview area */}
        {preview && (
          <div className="border-t bg-muted/30 p-4">
            <h4 className="mb-2 text-xs font-medium text-muted-foreground">拆分预览</h4>
            <div className="flex flex-col gap-2">
              {preview.map((p, i) => (
                <div key={i} className="rounded-md border bg-background p-2 text-xs">
                  <div className="mb-1 flex items-center gap-2">
                    <Badge variant="outline">片段 {i + 1}</Badge>
                    <span className="text-muted-foreground">~{p.token_count} tokens</span>
                  </div>
                  <p className="line-clamp-3 text-muted-foreground">{p.content}</p>
                </div>
              ))}
            </div>
          </div>
        )}
        {!preview && positions.length > 0 && (
          <div className="border-t bg-muted/30 p-4 text-xs text-muted-foreground">
            本地预估：
            {segments.map((s, i) => (
              <span key={i} className="ml-2">
                片段 {i + 1} ~{estimateTokens(content.slice(s.start, s.end))}t
              </span>
            ))}
            <span className="ml-3">（点击"预览"获取精确数据）</span>
          </div>
        )}
      </div>
    </div>
  )
}

function SplitMarker({ position, onRemove }: { position: number; onRemove: (p: number) => void }) {
  return (
    <span
      className="inline-flex items-center"
      onClick={(e) => e.stopPropagation()}
    >
      <span className="mx-0.5 inline-block h-4 w-0.5 bg-cyan-500" />
      <button
        type="button"
        className="mx-0.5 inline-flex size-4 items-center justify-center rounded-full bg-cyan-500/10 text-[10px] text-cyan-700 hover:bg-cyan-500/20"
        title="移除此分割点"
        onClick={() => onRemove(position)}
      >
        ×
      </button>
    </span>
  )
}
