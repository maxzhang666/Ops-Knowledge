import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { BookOpen, FileText, MessageSquare, Search } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { systemApi } from "@/api/system"

/**
 * Plan 34 M3 — Global search dialog triggered by ⌘K / Ctrl-K.
 *
 *   - Header 上嵌一个 Search button + 「⌘K」 hint
 *   - 弹出 Dialog 内输入框做 250ms debounce 拉 /system/search
 *   - 结果按 KB / 文档 / 会话 三组展示；上下方向键 + Enter 选择跳转
 */

interface Hit {
  kind: string
  id: string
  title: string
  subtitle: string
  href: string
}

export function GlobalSearch() {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const [hits, setHits] = useState<{ kbs: Hit[]; documents: Hit[]; conversations: Hit[] }>({
    kbs: [], documents: [], conversations: [],
  })
  const [loading, setLoading] = useState(false)
  const [activeIdx, setActiveIdx] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement | null>(null)

  // ⌘K / Ctrl-K shortcut
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  // Auto-focus when opening
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0)
  }, [open])

  // Debounced search
  useEffect(() => {
    if (!open) return
    if (q.trim().length < 2) {
      setHits({ kbs: [], documents: [], conversations: [] })
      return
    }
    const handle = setTimeout(async () => {
      setLoading(true)
      try {
        const r = await systemApi.search(q.trim(), 8)
        setHits(r)
        setActiveIdx(0)
      } catch {
        setHits({ kbs: [], documents: [], conversations: [] })
      } finally {
        setLoading(false)
      }
    }, 250)
    return () => clearTimeout(handle)
  }, [open, q])

  const flatHits = useMemo(
    () => [...hits.kbs, ...hits.documents, ...hits.conversations],
    [hits],
  )

  function navigateTo(hit: Hit) {
    setOpen(false)
    setQ("")
    navigate(hit.href)
  }

  function onInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, flatHits.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      const target = flatHits[activeIdx]
      if (target) navigateTo(target)
    } else if (e.key === "Escape") {
      setOpen(false)
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(true)}
        className="gap-2 text-xs text-muted-foreground"
        title="搜索 (⌘K / Ctrl-K)"
      >
        <Search className="size-3.5" />
        <span className="hidden sm:inline">搜索</span>
        <kbd className="hidden rounded border bg-muted px-1 text-[10px] sm:inline">⌘K</kbd>
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl p-0">
          <DialogHeader className="sr-only">
            <DialogTitle>全局搜索</DialogTitle>
          </DialogHeader>
          <div className="border-b px-3 py-2.5">
            <div className="flex items-center gap-2">
              <Search className="size-4 text-muted-foreground" />
              <Input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={onInputKeyDown}
                placeholder="搜索知识库 / 文档 / 会话..."
                className="h-9 border-0 bg-transparent shadow-none focus-visible:ring-0"
              />
            </div>
          </div>
          <div className="max-h-[60vh] overflow-y-auto p-1">
            {loading && (
              <p className="px-3 py-4 text-center text-xs text-muted-foreground">搜索中…</p>
            )}
            {!loading && q.trim().length >= 2 && flatHits.length === 0 && (
              <p className="px-3 py-6 text-center text-xs text-muted-foreground">未找到匹配项</p>
            )}
            {!loading && q.trim().length < 2 && (
              <p className="px-3 py-6 text-center text-xs text-muted-foreground">输入至少 2 个字符开始搜索</p>
            )}

            <Group title="知识库" icon={BookOpen} hits={hits.kbs} startIdx={0} activeIdx={activeIdx} onPick={navigateTo} />
            <Group title="文档" icon={FileText} hits={hits.documents} startIdx={hits.kbs.length} activeIdx={activeIdx} onPick={navigateTo} />
            <Group title="会话" icon={MessageSquare} hits={hits.conversations} startIdx={hits.kbs.length + hits.documents.length} activeIdx={activeIdx} onPick={navigateTo} />
          </div>
          <div className="border-t px-3 py-1.5 text-[10px] text-muted-foreground">
            ↑↓ 选择 · ↵ 打开 · Esc 关闭
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function Group({
  title, icon: Icon, hits, startIdx, activeIdx, onPick,
}: {
  title: string
  icon: typeof Search
  hits: Hit[]
  startIdx: number
  activeIdx: number
  onPick: (hit: Hit) => void
}) {
  if (hits.length === 0) return null
  return (
    <div className="mb-1">
      <div className="px-3 pb-1 pt-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        <Icon className="mr-1 inline size-3" /> {title}
      </div>
      <ul>
        {hits.map((h, i) => {
          const idx = startIdx + i
          return (
            <li key={`${h.kind}-${h.id}`}>
              <button
                type="button"
                className={`flex w-full flex-col items-start gap-0.5 rounded-md px-3 py-1.5 text-left text-sm hover:bg-muted ${activeIdx === idx ? "bg-muted" : ""}`}
                onClick={() => onPick(h)}
              >
                <span className="font-medium">{h.title}</span>
                {h.subtitle && (
                  <span className="line-clamp-1 text-[11px] text-muted-foreground">{h.subtitle}</span>
                )}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
