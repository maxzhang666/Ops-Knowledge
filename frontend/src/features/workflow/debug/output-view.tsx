import { useMemo, useState } from "react"
import { ChevronDown, ChevronRight, Code2, Copy, List } from "lucide-react"
import { toast } from "sonner"
import { StructuredValue } from "./structured-value"

/**
 * Output rendering for the Debug Panel.
 *
 *  1. `<OutputBlock>` — dispatches on shape: Answer-style {answer, references?}
 *     gets a friendly render; string scalars get fold / expand; object/array
 *     falls through to `<JsonView>`（纯手写，无外部依赖）。
 *  2. `<NodeOutputRow>` — collapsible per-node row for the Debug Panel node list.
 *
 * 说明：早前用过 Semi `<JsonViewer>`，它在 React StrictMode 下会重复挂载
 * Monaco 容器（两个 `json-viewer-container`），所以改回轻量版本。
 */


const TOKEN_CLS: Record<string, string> = {
  key: "text-blue-600 dark:text-blue-400",
  string: "text-green-700 dark:text-green-400",
  number: "text-orange-600 dark:text-orange-400",
  bool: "text-purple-600 dark:text-purple-400",
  null: "text-muted-foreground",
  punct: "text-muted-foreground",
}


function JsonView({ value, indent = 2 }: { value: unknown; indent?: number }) {
  const tree = useMemo(() => renderValue(value, indent, 0), [value, indent])
  return (
    <pre className="whitespace-pre-wrap break-words px-2 py-1.5 text-[11px] leading-relaxed">
      {tree}
    </pre>
  )
}


function renderValue(v: unknown, indent: number, depth: number): React.ReactNode {
  if (v === null) return <span className={TOKEN_CLS.null}>null</span>
  if (typeof v === "boolean") return <span className={TOKEN_CLS.bool}>{String(v)}</span>
  if (typeof v === "number") return <span className={TOKEN_CLS.number}>{v}</span>
  if (typeof v === "string") {
    return <span className={TOKEN_CLS.string}>"{v.replace(/\n/g, "\\n")}"</span>
  }
  if (Array.isArray(v)) {
    if (v.length === 0) return <span className={TOKEN_CLS.punct}>[]</span>
    const pad = " ".repeat((depth + 1) * indent)
    const outerPad = " ".repeat(depth * indent)
    return (
      <>
        <span className={TOKEN_CLS.punct}>[</span>{"\n"}
        {v.map((item, i) => (
          <span key={i}>
            {pad}
            {renderValue(item, indent, depth + 1)}
            {i < v.length - 1 && <span className={TOKEN_CLS.punct}>,</span>}
            {"\n"}
          </span>
        ))}
        {outerPad}<span className={TOKEN_CLS.punct}>]</span>
      </>
    )
  }
  if (typeof v === "object") {
    const entries = Object.entries(v as Record<string, unknown>)
    if (entries.length === 0) return <span className={TOKEN_CLS.punct}>{"{}"}</span>
    const pad = " ".repeat((depth + 1) * indent)
    const outerPad = " ".repeat(depth * indent)
    return (
      <>
        <span className={TOKEN_CLS.punct}>{"{"}</span>{"\n"}
        {entries.map(([k, vv], i) => (
          <span key={k}>
            {pad}
            <span className={TOKEN_CLS.key}>"{k}"</span>
            <span className={TOKEN_CLS.punct}>: </span>
            {renderValue(vv, indent, depth + 1)}
            {i < entries.length - 1 && <span className={TOKEN_CLS.punct}>,</span>}
            {"\n"}
          </span>
        ))}
        {outerPad}<span className={TOKEN_CLS.punct}>{"}"}</span>
      </>
    )
  }
  return <span>{String(v)}</span>
}


export function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text)
    .then(() => toast.success("已复制"))
    .catch(() => toast.error("复制失败"))
}


/** Best-effort text extraction for the copy button. */
function valueToText(v: unknown): string {
  if (typeof v === "string") return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v ?? "")
  }
}


// -----------------------------------------------------------------------
// OutputBlock: the actual per-node / overall output visual.

const FOLD_LINE_THRESHOLD = 12


export function OutputBlock({
  value,
  label,
}: {
  value: unknown
  label?: string
}) {
  const [expanded, setExpanded] = useState(false)
  const [rawMode, setRawMode] = useState(false)
  const asText = useMemo(() => valueToText(value), [value])
  const lineCount = asText.split("\n").length
  const long = lineCount > FOLD_LINE_THRESHOLD

  // Answer-style output: {answer: string, references?: [...]}
  const isAnswerShape =
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    typeof (value as Record<string, unknown>).answer === "string"

  if (isAnswerShape) {
    const { answer, references } = value as {
      answer: string
      references?: Array<Record<string, unknown>>
    }
    return (
      <div className="space-y-2">
        {label && (
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase text-muted-foreground">{label}</span>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
              onClick={() => copyToClipboard(answer)}
            >
              <Copy className="size-3" /> 复制
            </button>
          </div>
        )}
        <div className="whitespace-pre-wrap rounded border bg-background p-2 text-xs">
          {answer || <span className="text-muted-foreground">（空回复）</span>}
        </div>
        {references && references.length > 0 && (
          <ReferenceList refs={references} />
        )}
      </div>
    )
  }

  // String scalar → plain pre with optional fold
  if (typeof value === "string") {
    const shown = !long || expanded ? value : value.split("\n").slice(0, FOLD_LINE_THRESHOLD).join("\n")
    return (
      <div className="space-y-1">
        {label && (
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase text-muted-foreground">{label}</span>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
              onClick={() => copyToClipboard(value)}
            >
              <Copy className="size-3" /> 复制
            </button>
          </div>
        )}
        <pre className="whitespace-pre-wrap break-words rounded border bg-background p-2 text-xs">
          {shown}
          {long && !expanded && "\n..."}
        </pre>
        {long && (
          <button
            type="button"
            onClick={() => setExpanded((x) => !x)}
            className="text-[10px] text-primary hover:underline"
          >
            {expanded ? "折叠" : `展开（共 ${lineCount} 行）`}
          </button>
        )}
      </div>
    )
  }

  // Generic object/array → 默认走"结构化视图"（面向普通用户：字段名+值的表单式
  // 布局，无 JSON 符号）；右上角可切换回原始 JSON 视图供技术人员排查。
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        {label && (
          <span className="text-[10px] uppercase text-muted-foreground">{label}</span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setRawMode((x) => !x)}
            className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
            title={rawMode ? "切换为结构化视图" : "切换为原始 JSON"}
          >
            {rawMode ? <List className="size-3" /> : <Code2 className="size-3" />}
            {rawMode ? "结构化" : "原始"}
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
            onClick={() => copyToClipboard(asText)}
          >
            <Copy className="size-3" /> 复制
          </button>
        </div>
      </div>
      <div
        className="overflow-auto rounded border bg-background"
        style={{ maxHeight: expanded ? 480 : 260 }}
      >
        {rawMode ? (
          <div className="font-mono">
            <JsonView value={value} />
          </div>
        ) : (
          <div className="p-2 text-[11px]">
            <StructuredValue value={value} />
          </div>
        )}
      </div>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((x) => !x)}
          className="text-[10px] text-primary hover:underline"
        >
          {expanded ? "收起" : "展开"}
        </button>
      )}
    </div>
  )
}


function ReferenceList({ refs }: { refs: Array<Record<string, unknown>> }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded border bg-muted/30">
      <button
        type="button"
        onClick={() => setOpen((x) => !x)}
        className="flex w-full items-center gap-1 px-2 py-1 text-[11px] font-medium"
      >
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        引用 {refs.length} 条
      </button>
      {open && (
        <div className="space-y-1 border-t p-2">
          {refs.map((r, i) => (
            <div key={i} className="rounded bg-background p-1.5 text-[11px]">
              <div className="font-medium">
                {String(r.document_title ?? r.title ?? r.id ?? `#${i}`)}
              </div>
              <div className="text-muted-foreground">
                {String(r.content_preview ?? r.content ?? "").slice(0, 200)}
              </div>
              {typeof r.score === "number" && (
                <div className="mt-0.5 text-[10px] text-muted-foreground">
                  score {r.score.toFixed(3)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// -----------------------------------------------------------------------
// NodeOutputRow: collapsible row used in Debug Panel's per-node list.

export function NodeOutputRow({
  nodeId,
  nodeType,
  status,
  error,
  output,
  statusClass,
}: {
  nodeId: string
  nodeType: string
  status: string
  error?: string
  output?: unknown
  statusClass: string
}) {
  const [open, setOpen] = useState(false)
  const hasDetails = output !== undefined || error !== undefined

  return (
    <div className="rounded border bg-background">
      <div className="flex items-center gap-2 px-2 py-1">
        <button
          type="button"
          className="inline-flex size-4 items-center justify-center text-muted-foreground hover:text-foreground"
          onClick={() => setOpen((x) => !x)}
          disabled={!hasDetails}
          aria-label={open ? "折叠" : "展开"}
        >
          {hasDetails
            ? (open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />)
            : <span className="size-3.5" />}
        </button>
        <span className="min-w-0 flex-1 truncate" title={nodeId}>
          <span className="text-muted-foreground">{nodeType}</span>
          <span className="mx-1 text-muted-foreground">·</span>
          <span>{nodeId}</span>
        </span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusClass}`}>
          {status}
        </span>
      </div>
      {open && hasDetails && (
        <div className="space-y-1 border-t p-2">
          {error && (
            <div className="rounded bg-red-50 p-1.5 text-[11px] text-red-900 dark:bg-red-950 dark:text-red-200">
              {error}
            </div>
          )}
          {output !== undefined && (
            <OutputBlock value={output} label="output" />
          )}
        </div>
      )}
    </div>
  )
}
