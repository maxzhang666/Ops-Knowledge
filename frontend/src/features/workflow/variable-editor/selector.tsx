import { useEffect, useMemo, useRef, useState } from "react"
import { ChevronDown, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { useEditorStore } from "../store"
import { computeUpstream, type VariableSource } from "./upstream"

/**
 * 统一变量选择器 — "选一个变量"场景（区别于 VariableEditor 的"文本+变量混排"）。
 *
 * 交互（Notion mention 风格）：
 *   - 未选中 → 虚框按钮「选择变量」
 *   - 已选中 → chip：类别色点 + 节点名.字段 + × 清除
 *   - 点击弹 popover：搜索框 + 按节点分组 + 字段旁类型徽标
 *
 * 健壮性：强制只能从列表选。变量不在列表（上游未连）时用户无法手动输入，
 * 避免写死一个不存在的 selector 导致执行时 resolve 失败。
 *
 * 值格式：DSL selector 路径数组 ["node_id", "field"]；未选为 undefined。
 */
interface Props {
  currentNodeId: string
  value: string[] | undefined
  onChange: (v: string[] | undefined) => void
  filterType?: string          // "string" / "number" / "boolean" / "any"（默认不筛选）
  placeholder?: string
}


export function VariableSelector({
  currentNodeId,
  value,
  onChange,
  filterType,
  placeholder = "选择变量",
}: Props) {
  const nodes = useEditorStore((s) => s.nodes)
  const edges = useEditorStore((s) => s.edges)
  const catalog = useEditorStore((s) => s.catalog)

  const sources = useMemo(
    () => computeUpstream(currentNodeId, nodes, edges, catalog, []),
    [currentNodeId, nodes, edges, catalog],
  )

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const rootRef = useRef<HTMLDivElement | null>(null)

  // 点击外部关闭 popover
  useEffect(() => {
    if (!open) return
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [open])

  // 当前选中变量的展示 label
  const current = useMemo(() => {
    if (!value || value.length < 2) return null
    const [nodeId, field] = value
    const src = sources.find((s) => s.node_id === nodeId)
    // 上游节点还存在 → 用节点中文名；否则显示原始 id 作为兜底
    const nodeLabel = src?.label ?? nodeId
    const fieldEntry = src?.fields.find((f) => f.name === field)
    return {
      nodeLabel,
      field,
      type: fieldEntry?.type ?? "?",
      stale: !src || !fieldEntry,  // 上游已删除/重命名的陈旧引用 → 红色提示
    }
  }, [value, sources])

  function pick(nodeId: string, field: string) {
    onChange([nodeId, field])
    setOpen(false)
    setQuery("")
  }

  function clear(e: React.MouseEvent) {
    e.stopPropagation()
    onChange(undefined)
  }

  return (
    <div ref={rootRef} className="relative inline-block min-w-0">
      {current ? (
        <button
          type="button"
          onClick={() => setOpen((x) => !x)}
          className={cn(
            "inline-flex max-w-full items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors",
            current.stale
              ? "border-destructive/60 bg-destructive/10 text-destructive hover:bg-destructive/20"
              : "border-primary/40 bg-primary/10 text-primary hover:bg-primary/20",
          )}
          title={current.stale ? "变量来源已变更，请重新选择" : `${current.nodeLabel}.${current.field}（${current.type}）`}
        >
          <span className="size-1.5 shrink-0 rounded-full bg-current" />
          <span className="min-w-0 truncate">
            <span className="font-medium">{current.nodeLabel}</span>
            <span className="opacity-70">.{current.field}</span>
          </span>
          <span
            role="button"
            aria-label="清除"
            tabIndex={-1}
            onClick={clear}
            className="-mr-1 ml-0.5 inline-flex size-3.5 shrink-0 items-center justify-center rounded hover:bg-current/20"
          >
            <X className="size-3" />
          </span>
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setOpen((x) => !x)}
          className="inline-flex items-center gap-1 rounded-md border border-dashed px-2 py-1 text-[11px] text-muted-foreground hover:border-primary/40 hover:bg-muted hover:text-foreground"
        >
          <span>{placeholder}</span>
          <ChevronDown className="size-3" />
        </button>
      )}

      {open && (
        <VariableList
          sources={sources}
          query={query}
          onQueryChange={setQuery}
          filterType={filterType}
          onPick={pick}
        />
      )}
    </div>
  )
}


function VariableList({
  sources,
  query,
  onQueryChange,
  filterType,
  onPick,
}: {
  sources: VariableSource[]
  query: string
  onQueryChange: (v: string) => void
  filterType?: string
  onPick: (nodeId: string, field: string) => void
}) {
  const q = query.toLowerCase()
  const matchesType = (t: string) =>
    !filterType || filterType === "any" || t === filterType || t === "any"

  // 按节点分组过滤
  const groups = sources
    .map((s) => ({
      source: s,
      fields: s.fields.filter(
        (f) =>
          matchesType(f.type) &&
          (!q ||
            f.name.toLowerCase().includes(q) ||
            s.label.toLowerCase().includes(q)),
      ),
    }))
    .filter((g) => g.fields.length > 0)

  const empty = groups.length === 0

  return (
    <div
      className="absolute left-0 top-full z-50 mt-1 w-72 overflow-hidden rounded-md border bg-popover shadow-md"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="border-b p-1.5">
        <input
          autoFocus
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="搜索变量..."
          className="h-7 w-full rounded border bg-background px-2 text-xs outline-none focus:ring-1 focus:ring-primary/40"
        />
      </div>
      <div className="max-h-64 overflow-y-auto p-1">
        {empty ? (
          <div className="px-2 py-3 text-center text-[11px] text-muted-foreground">
            {sources.length === 0
              ? "当前节点无上游，请先连接其他节点"
              : "无匹配变量"}
          </div>
        ) : (
          groups.map((g) => (
            <div key={g.source.node_id} className="mb-1">
              <div className="px-2 py-1 text-[10px] font-medium uppercase text-muted-foreground">
                {g.source.label}
              </div>
              {g.fields.map((f) => (
                <button
                  key={`${g.source.node_id}.${f.name}`}
                  type="button"
                  onClick={() => onPick(g.source.node_id, f.name)}
                  className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-xs hover:bg-muted"
                >
                  <span className="min-w-0 truncate font-medium">{f.name}</span>
                  <span className="shrink-0 rounded bg-muted px-1 text-[9px] text-muted-foreground">
                    {f.type}
                  </span>
                </button>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
