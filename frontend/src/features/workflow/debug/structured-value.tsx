import { useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"

/**
 * 结构化数据展示 — 面向非开发人员的友好视图。
 *
 * 设计原则：
 *  - 不显示 JSON 语法符号（`{}`, `[]`, `:`, `,`, 引号）
 *  - 对象按"字段名 → 值"一行一行展示
 *  - 列表用「第 N 项」标记
 *  - 嵌套结构默认展开前两层，再深需用户点击展开
 *  - 类型用颜色和小图标暗示（文本/数字/开关/空），但不强塞术语
 */

interface Props {
  value: unknown
  depth?: number
}


export function StructuredValue({ value, depth = 0 }: Props) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">（空）</span>
  }

  if (typeof value === "string") {
    return <StringValue text={value} />
  }

  if (typeof value === "number") {
    return <span className="font-mono text-orange-600 dark:text-orange-400">{value}</span>
  }

  if (typeof value === "boolean") {
    return (
      <span className="font-medium text-purple-600 dark:text-purple-400">
        {value ? "是" : "否"}
      </span>
    )
  }

  if (Array.isArray(value)) {
    return <ArrayValue items={value} depth={depth} />
  }

  if (typeof value === "object") {
    return (
      <ObjectValue
        entries={Object.entries(value as Record<string, unknown>)}
        depth={depth}
      />
    )
  }

  return <span>{String(value)}</span>
}


function StringValue({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const long = text.length > 120 || text.split("\n").length > 4
  if (!long) {
    return (
      <span className="whitespace-pre-wrap break-words text-foreground">
        {text}
      </span>
    )
  }
  const shown = expanded ? text : text.slice(0, 120) + "…"
  return (
    <span>
      <span className="whitespace-pre-wrap break-words text-foreground">{shown}</span>
      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        className="ml-1 text-[10px] text-primary hover:underline"
      >
        {expanded ? "收起" : "展开"}
      </button>
    </span>
  )
}


function ObjectValue({
  entries,
  depth,
}: {
  entries: Array<[string, unknown]>
  depth: number
}) {
  const [open, setOpen] = useState(depth < 2)

  if (entries.length === 0) {
    return <span className="text-muted-foreground italic">（空对象）</span>
  }

  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => setOpen((x) => !x)}
        className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        {open ? "收起" : `${entries.length} 个字段`}
      </button>
      {open && (
        <div className="mt-0.5 space-y-1 border-l border-border/60 pl-2.5">
          {entries.map(([k, v]) => (
            <Row key={k} label={k} value={v} depth={depth} />
          ))}
        </div>
      )}
    </div>
  )
}


function ArrayValue({
  items,
  depth,
}: {
  items: unknown[]
  depth: number
}) {
  const [open, setOpen] = useState(depth < 2)

  if (items.length === 0) {
    return <span className="text-muted-foreground italic">（空列表）</span>
  }

  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => setOpen((x) => !x)}
        className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        {open ? "收起" : `共 ${items.length} 项`}
      </button>
      {open && (
        <div className="mt-0.5 space-y-1 border-l border-border/60 pl-2.5">
          {items.map((item, i) => (
            <Row key={i} label={`第 ${i + 1} 项`} value={item} depth={depth} />
          ))}
        </div>
      )}
    </div>
  )
}


/** 一行：左侧标签，右侧结构化值。简单值同行，复合值换行缩进。 */
function Row({
  label,
  value,
  depth,
}: {
  label: string
  value: unknown
  depth: number
}) {
  const isComplex =
    value !== null &&
    typeof value === "object" // 含数组

  return (
    <div className={isComplex ? "flex flex-col gap-0.5" : "flex items-start gap-2"}>
      <span
        className={`shrink-0 text-[11px] font-medium text-primary/80 ${
          isComplex ? "" : "min-w-[4rem]"
        }`}
      >
        {label}
      </span>
      <div className={`min-w-0 flex-1 text-[11px] ${isComplex ? "pl-1" : ""}`}>
        <StructuredValue value={value} depth={depth + 1} />
      </div>
    </div>
  )
}
