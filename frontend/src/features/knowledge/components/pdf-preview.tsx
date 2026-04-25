import { useCallback, useEffect, useRef, useState } from "react"
import * as pdfjs from "pdfjs-dist"
import "pdfjs-dist/web/pdf_viewer.css"
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist"
import { Loader2 } from "lucide-react"

import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { knowledgeApi } from "@/api/knowledge"

// pdf.js worker — Vite ?url 把 worker 文件作为静态资产 emit；浏览器无需联网
import workerUrl from "pdfjs-dist/build/pdf.worker.mjs?url"
;(pdfjs as unknown as { GlobalWorkerOptions: { workerSrc: string } }).GlobalWorkerOptions.workerSrc = workerUrl

/**
 * PDF 预览（Plan 32 M2）—— 用 pdf.js 渲染所有页面，并基于检索片段
 * 内容做 textLayer 高亮 + 自动滚动定位。
 *
 *   - 不分页加载（多数文档 < 200 页，整体渲染体验最好）
 *   - 高亮策略：把传入的 highlightText 拆词、做归一化匹配；命中则在
 *     textLayer 上叠加 mark 元素
 *   - canvas 默认 1.5 缩放（高 DPR 屏幕由 transformList 自动适配）
 */

interface PdfPreviewProps {
  kbId: string
  docId: string
  highlightText?: string  // 检索片段内容，用于在 PDF 中高亮 + 滚动
}

const RENDER_SCALE = 1.5

export function PdfPreview({ kbId, docId, highlightText }: PdfPreviewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [progress, setProgress] = useState({ rendered: 0, total: 0 })

  // 1) Fetch PDF blob → load with pdf.js
  useEffect(() => {
    let cancelled = false
    let toClose: PDFDocumentProxy | null = null
    setLoading(true)
    setError(null)
    setDoc(null)
    knowledgeApi.downloadDocument(kbId, docId)
      .then(async (blob) => {
        const buf = await blob.arrayBuffer()
        if (cancelled) return
        const task = pdfjs.getDocument({ data: buf })
        const pdfDoc = await task.promise
        if (cancelled) {
          await pdfDoc.destroy()
          return
        }
        toClose = pdfDoc
        setDoc(pdfDoc)
        setProgress({ rendered: 0, total: pdfDoc.numPages })
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "PDF 加载失败")
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => {
      cancelled = true
      void toClose?.destroy()
    }
  }, [kbId, docId])

  // 2) Render all pages sequentially after doc is ready
  const renderPages = useCallback(async () => {
    if (!doc || !containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ""  // reset on re-render

    let firstHighlightedPage: HTMLDivElement | null = null
    const needles = (highlightText || "")
      .split(/[\s,，。\n]+/)
      .map((w) => w.trim())
      .filter((w) => w.length >= 4)
      .slice(0, 8)  // 最多 8 个关键词参与匹配，避免超长卡顿

    for (let i = 1; i <= doc.numPages; i++) {
      const page: PDFPageProxy = await doc.getPage(i)
      const viewport = page.getViewport({ scale: RENDER_SCALE })

      const pageWrap = document.createElement("div")
      pageWrap.className = "relative mx-auto my-4 shadow-sm"
      pageWrap.style.width = `${viewport.width}px`
      pageWrap.style.height = `${viewport.height}px`

      const canvas = document.createElement("canvas")
      canvas.width = viewport.width
      canvas.height = viewport.height
      canvas.className = "block"
      pageWrap.appendChild(canvas)

      const textLayer = document.createElement("div")
      textLayer.className = "textLayer absolute inset-0"
      textLayer.style.setProperty("--scale-factor", String(RENDER_SCALE))
      pageWrap.appendChild(textLayer)

      container.appendChild(pageWrap)

      const ctx = canvas.getContext("2d")
      if (!ctx) continue
      await page.render({ canvasContext: ctx, viewport, canvas }).promise

      // text layer for selection + highlighting
      const textContent = await page.getTextContent()
      // pdf.js >=4 ships TextLayer class
      const TextLayerCtor = (pdfjs as unknown as { TextLayer?: new (args: unknown) => { render: () => Promise<void> } }).TextLayer
      if (TextLayerCtor) {
        const tl = new TextLayerCtor({ textContentSource: textContent, container: textLayer, viewport })
        await tl.render()
      }

      if (needles.length > 0) {
        const hit = highlightInLayer(textLayer, needles)
        if (hit && !firstHighlightedPage) {
          firstHighlightedPage = pageWrap
        }
      }
      setProgress({ rendered: i, total: doc.numPages })
    }

    if (firstHighlightedPage) {
      firstHighlightedPage.scrollIntoView({ behavior: "smooth", block: "start" })
    }
  }, [doc, highlightText])

  useEffect(() => {
    if (doc) void renderPages()
  }, [doc, renderPages])

  if (loading && !doc) return <LoadingSpinner className="py-16" />
  if (error) return <p className="p-6 text-sm text-destructive">加载失败：{error}</p>
  if (!doc) return null

  return (
    <div className="flex h-full flex-col">
      {progress.rendered < progress.total && (
        <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          渲染中 {progress.rendered}/{progress.total}
        </div>
      )}
      <div ref={containerRef} className="flex-1 overflow-auto bg-muted/30" />
    </div>
  )
}

/**
 * 在 textLayer 内寻找含 needle 子串的 span，包裹一个 <mark>。
 * 返回是否命中至少一处。
 */
function highlightInLayer(textLayer: HTMLDivElement, needles: string[]): boolean {
  let hit = false
  const spans = textLayer.querySelectorAll("span")
  spans.forEach((span) => {
    const text = span.textContent ?? ""
    for (const n of needles) {
      if (!n) continue
      const idx = text.indexOf(n)
      if (idx === -1) continue
      // wrap matched substring; preserve original layout by re-rendering span content
      const before = text.slice(0, idx)
      const matched = text.slice(idx, idx + n.length)
      const after = text.slice(idx + n.length)
      span.textContent = ""
      if (before) span.appendChild(document.createTextNode(before))
      const mark = document.createElement("mark")
      mark.className = "bg-yellow-300/70 px-0.5"
      mark.textContent = matched
      span.appendChild(mark)
      if (after) span.appendChild(document.createTextNode(after))
      hit = true
      break  // 单 span 高亮一次即可
    }
  })
  return hit
}
