import { useEffect, useState } from "react"
import { MarkdownRender } from "@douyinfe/semi-ui"
import { markdownCodeBlockComponents } from "@/components/shared/markdown-code-block"

import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { EmptyState } from "@/components/shared/empty-state"
import { knowledgeApi } from "@/api/knowledge"
import { PdfPreview } from "./pdf-preview"

interface DocumentPreviewProps {
  kbId: string
  docId: string
  sourceType: string  // "markdown" | "txt" | "csv" | "pdf" — determines rendering
  title: string
  // Plan 32 — 检索到本文档片段的内容；用于 PDF 高亮+滚动定位
  highlightText?: string
}

// Source types the backend /preview endpoint supports.
// Anything else shows an "预览暂不支持" placeholder.
const PREVIEWABLE = new Set(["markdown", "txt", "csv"])

/**
 * Plain-content preview for MD/TXT/CSV documents. Backend endpoint reads the
 * original file from MinIO and returns raw text; we render per type:
 *   - markdown: Semi MarkdownRender (same as chat bubbles)
 *   - txt:      <pre> monospace
 *   - csv:      parsed into <table>
 */
export function DocumentPreview({ kbId, docId, sourceType, title, highlightText }: DocumentPreviewProps) {
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const lower = sourceType.toLowerCase()
  const isPdf = lower === "pdf"
  const canPreview = isPdf || PREVIEWABLE.has(lower)

  useEffect(() => {
    if (!canPreview || isPdf) { setLoading(false); return }
    let cancelled = false
    setLoading(true)
    setError(null)
    knowledgeApi.previewDocument(kbId, docId)
      .then((res) => { if (!cancelled) setContent(res.content) })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "加载失败") })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [kbId, docId, canPreview, isPdf])

  if (isPdf) {
    return <PdfPreview kbId={kbId} docId={docId} highlightText={highlightText} />
  }
  if (!canPreview) {
    return (
      <EmptyState
        title="预览暂不支持"
        description={`${sourceType.toUpperCase()} 类型不支持在线预览，请下载后查看`}
      />
    )
  }
  if (loading) return <LoadingSpinner className="py-16" />
  if (error) return <p className="p-6 text-sm text-destructive">加载失败：{error}</p>
  if (!content) return <EmptyState title="内容为空" description="该文件没有可预览内容" />

  if (sourceType === "markdown") {
    return (
      <div className="prose prose-sm max-w-none p-6 dark:prose-invert">
        <MarkdownRender raw={content} format="md" components={markdownCodeBlockComponents} />
      </div>
    )
  }
  if (sourceType === "csv") {
    return <CsvTable content={content} />
  }
  // txt fallback
  return (
    <pre className="whitespace-pre-wrap p-6 text-sm leading-relaxed font-mono" aria-label={title}>
      {content}
    </pre>
  )
}

function CsvTable({ content }: { content: string }) {
  // Minimal CSV parse: assumes comma delimiter, no embedded newlines in quotes.
  // Good enough for preview — full CSV handling belongs to a data-import flow.
  const rows = content.split(/\r?\n/).filter((l) => l.trim().length > 0).map((line) => {
    // Split on commas, respecting double-quoted fields
    const cells: string[] = []
    let cur = ""
    let inQuote = false
    for (let i = 0; i < line.length; i++) {
      const ch = line[i]
      if (ch === '"') { inQuote = !inQuote; continue }
      if (ch === "," && !inQuote) { cells.push(cur); cur = ""; continue }
      cur += ch
    }
    cells.push(cur)
    return cells
  })
  const [header, ...body] = rows
  if (!header) return <EmptyState title="内容为空" description="未检测到 CSV 数据" />

  return (
    <div className="overflow-auto p-4">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="border-b bg-muted">
            {header.map((h, i) => (
              <th key={i} className="px-2 py-1.5 text-left font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, i) => (
            <tr key={i} className="border-b hover:bg-muted/40">
              {row.map((c, j) => (
                <td key={j} className="px-2 py-1 font-mono text-[11px]">{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
