import { useEffect, useState } from "react"
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react"
import { Loader2, CheckCircle2, XCircle, MinusCircle, PauseCircle } from "lucide-react"
import { useEditorStore } from "./store"
import { categoryCn, nodeNameCn } from "./i18n"
import { NodeIcon } from "./node-icons"

interface Data extends Record<string, unknown> {
  nodeType: string
  typeVersion: string
  config: Record<string, unknown>
  blocks?: unknown
}

type OpskNodeType = Node<Data, "opsk">

const EXEC_RING: Record<string, string> = {
  running: "ring-2 ring-blue-500 animate-pulse",
  waiting: "ring-2 ring-orange-500 animate-pulse",
  succeeded: "ring-2 ring-green-500",
  failed: "ring-2 ring-red-500",
  skipped: "ring-2 ring-gray-300",
  cancelled: "ring-2 ring-yellow-500",
}

// 左侧色带颜色 — 一眼分辨节点类别。
const CATEGORY_ACCENT: Record<string, string> = {
  trigger: "bg-emerald-500",
  llm: "bg-blue-500",
  knowledge: "bg-violet-500",
  logic: "bg-amber-500",
  output: "bg-slate-500",
  agent: "bg-pink-500",
  memory: "bg-yellow-500",
  extension: "bg-cyan-500",
}


export function OpskNode({ id, data, selected }: NodeProps<OpskNodeType>) {
  const catalog = useEditorStore((s) => s.catalog)
  const execStatus = useEditorStore((s) => s.execution?.nodes[id])
  const startedAt = useEditorStore((s) => s.execution?.nodeStartedAt[id])
  const durationMs = useEditorStore((s) => s.execution?.nodeDurationMs[id])
  const entry = catalog.find((c) => c.manifest.type === data.nodeType)
  const manifest = entry?.manifest
  const isTrigger = manifest?.category === "trigger"
  const isTerminal = manifest?.is_terminal
  const branches = deriveBranches(data)
  const summary = deriveSummary(data)
  const accentCls = CATEGORY_ACCENT[manifest?.category ?? ""] ?? "bg-muted-foreground/40"
  const execClass = execStatus ? EXEC_RING[execStatus] ?? "" : ""

  const elapsed = useRunningElapsed(execStatus, startedAt)
  const timingText = formatDuration(durationMs ?? elapsed)

  return (
    <div
      className={`relative flex rounded-md border bg-background text-xs shadow-sm ${
        selected ? "ring-2 ring-ring" : execClass
      }`}
      style={{ minWidth: 200 }}
    >
      {/* 左侧色带 — 按 category 区分；宽度 3px。自身圆角贴合外框，避免外层
          overflow-hidden（那会把 Handle 的外半圆也裁掉）。 */}
      <div className={`w-[3px] shrink-0 rounded-l-[5px] ${accentCls}`} />

      <div className="min-w-0 flex-1 px-2.5 py-2">
        {!isTrigger && <Handle type="target" position={Position.Left} />}

        {/* 标题行：节点图标 + 节点名 + 类别上标 + 执行状态图标 */}
        <div className="flex items-center gap-1.5">
          <NodeIcon type={data.nodeType} className="size-3.5 shrink-0 text-foreground/70" />
          <span className="min-w-0 flex-1 truncate font-medium">
            {nodeNameCn(data.nodeType, manifest?.name)}
            {manifest?.category && (
              <sup className="ml-1 rounded bg-muted px-1 text-[8px] font-normal text-muted-foreground">
                {categoryCn(manifest.category)}
              </sup>
            )}
          </span>
          {execStatus && <StatusIcon status={execStatus} />}
        </div>

        {/* 关键配置摘要 — 每种节点 1-2 行，一眼看出它在干什么 */}
        {summary && summary.length > 0 && (
          <div className="mt-1 space-y-0.5 rounded bg-muted/40 px-1.5 py-0.5 text-[10px] text-foreground/70">
            {summary.map((line, i) => (
              <div key={i} className="truncate" title={line}>
                {line}
              </div>
            ))}
          </div>
        )}

        {/* node id + 耗时（次要信息） */}
        <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
          <span className="truncate">{id}</span>
          {timingText && (
            <span className={execStatus === "running" ? "text-blue-600" : ""}>
              {timingText}
            </span>
          )}
        </div>

        {/* 分支节点：每个分支一行 label + 右侧 handle；普通节点只有一个默认 handle */}
        {branches.length > 0 ? (
          <div className="-mr-2.5 mt-2 flex flex-col gap-1">
            {branches.map((b) => (
              <div
                key={b.id}
                className="relative flex items-center justify-end rounded-l bg-muted/60 py-0.5 pl-2 pr-3 text-[10px]"
                title={b.label}
              >
                <span className="max-w-[130px] truncate text-foreground/80">
                  {b.label}
                </span>
                <Handle
                  type="source"
                  position={Position.Right}
                  id={b.id}
                  style={{ top: "50%", right: -4 }}
                />
              </div>
            ))}
          </div>
        ) : !isTerminal ? (
          <Handle type="source" position={Position.Right} />
        ) : null}
      </div>
    </div>
  )
}


function StatusIcon({ status }: { status: string }) {
  if (status === "running") return <Loader2 className="size-3 animate-spin text-blue-600" />
  if (status === "waiting") return <PauseCircle className="size-3 text-orange-600" />
  if (status === "succeeded") return <CheckCircle2 className="size-3 text-green-600" />
  if (status === "failed") return <XCircle className="size-3 text-red-600" />
  if (status === "skipped") return <MinusCircle className="size-3 text-muted-foreground" />
  return null
}


function useRunningElapsed(
  status: string | undefined, startedAt: number | undefined,
): number | undefined {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (status !== "running" || !startedAt) return
    const h = window.setInterval(() => setNow(Date.now()), 200)
    return () => window.clearInterval(h)
  }, [status, startedAt])
  if (status !== "running" || !startedAt) return undefined
  return Math.max(0, now - startedAt)
}


function formatDuration(ms: number | undefined): string | null {
  if (ms === undefined || ms < 0) return null
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}


// ---- 分支 & 摘要推导 ---------------------------------------------------------

interface Branch {
  id: string
  label: string
}

function deriveBranches(data: Data): Branch[] {
  const cfg = data.config as Record<string, unknown>
  if (data.nodeType === "if-else") {
    const conds =
      (cfg.conditions as
        | Array<{
            id: string
            rules?: Array<{ variable?: unknown; operator?: string; value?: unknown }>
          }>
        | undefined) ?? []
    return [
      ...conds.map((c) => ({
        id: c.id,
        label: firstRuleLabel(c.rules) || c.id,
      })),
      { id: "else", label: "否则" },
    ]
  }
  if (data.nodeType === "question-classifier") {
    const cats =
      (cfg.categories as Array<{ id: string; name?: string }> | undefined) ?? []
    return cats.map((c) => ({
      id: c.id,
      label: c.name?.trim() ? c.name : c.id,
    }))
  }
  return []
}

const OP_CN: Record<string, string> = {
  eq: "=", neq: "≠", gt: ">", gte: "≥", lt: "<", lte: "≤",
  contains: "包含", not_contains: "不包含",
  is_empty: "为空", not_empty: "非空",
  starts_with: "以…开头", ends_with: "以…结尾",
}

function firstRuleLabel(
  rules?: Array<{ variable?: unknown; operator?: string; value?: unknown }>,
): string {
  if (!rules || rules.length === 0) return ""
  const r = rules[0]
  const v = Array.isArray(r.variable)
    ? r.variable.join(".")
    : typeof r.variable === "string" ? r.variable : "?"
  const op = OP_CN[r.operator ?? ""] ?? r.operator ?? ""
  const val =
    r.value === undefined || r.value === null || r.value === ""
      ? ""
      : String(r.value)
  const parts = [v, op, val].filter(Boolean)
  const text = parts.join(" ")
  return text.length > 28 ? text.slice(0, 26) + "…" : text
}


/**
 * 节点卡片的摘要信息 — 每个节点返回 1-2 行描述性内容，非开发人员也能看懂在做什么。
 * 全部已注册节点都覆盖；未知类型才返回 null。
 */
function deriveSummary(data: Data): string[] | null {
  const cfg = data.config as Record<string, unknown>
  const inputs = (cfg.inputs as Record<string, unknown> | undefined) ?? {}
  const t = data.nodeType
  const lines: string[] = []

  switch (t) {
    case "start": {
      const vars = (cfg.variables as Array<{ name?: string }> | undefined) ?? []
      if (vars.length > 0) {
        const names = vars.map((v) => v.name).filter(Boolean).slice(0, 3).join("、")
        lines.push(`输入变量：${names}${vars.length > 3 ? `…（共 ${vars.length}）` : ""}`)
      } else {
        lines.push("触发：对话 / Webhook / API")
      }
      break
    }

    case "llm": {
      const model = cfg.model_name as string | undefined
      if (model) lines.push(`模型：${model}`)
      const prompt = cfg.prompt_template as string | undefined
      if (prompt?.trim()) lines.push(`提示词：${truncate(oneLine(prompt), 22)}`)
      break
    }

    case "question-classifier": {
      const model = cfg.model_name as string | undefined
      const cats = (cfg.categories as Array<unknown> | undefined) ?? []
      if (model) lines.push(`模型：${model}`)
      if (cats.length > 0) lines.push(`类别 × ${cats.length}`)
      break
    }

    case "parameter-extractor": {
      const model = cfg.model_name as string | undefined
      const params = (cfg.parameters as Array<{ name?: string }> | undefined) ?? []
      if (model) lines.push(`模型：${model}`)
      if (params.length > 0) {
        const names = params.map((p) => p.name).filter(Boolean).slice(0, 3).join("、")
        lines.push(`参数：${names}${params.length > 3 ? `…（共 ${params.length}）` : ""}`)
      }
      break
    }

    case "knowledge-retrieval": {
      const kbs = (cfg.knowledge_base_ids as string[] | undefined) ?? []
      if (kbs.length > 0) lines.push(`知识库 × ${kbs.length}`)
      const topK = cfg.top_k as number | undefined
      const mode = cfg.retrieval_mode as string | undefined
      if (topK || mode) {
        const bits: string[] = []
        if (mode) bits.push(mode === "hybrid" ? "混合检索" : mode === "semantic" ? "向量检索" : mode)
        if (topK) bits.push(`Top ${topK}`)
        lines.push(bits.join(" · "))
      }
      break
    }

    case "answer": {
      const ans = inputs.answer
      if (typeof ans === "string" && ans.trim()) {
        lines.push(`回复：${truncate(oneLine(ans), 22)}`)
      } else if (ans) {
        lines.push("回复：引用上游输出")
      }
      const stream = cfg.stream
      if (stream === false) lines.push("流式：关闭")
      break
    }

    case "if-else": {
      const conds = (cfg.conditions as Array<unknown> | undefined) ?? []
      lines.push(`分支 × ${conds.length + 1}（含「否则」）`)
      break
    }

    case "http-request": {
      const method = ((cfg.method as string | undefined) ?? "GET").toUpperCase()
      const url = (cfg.url as string | undefined) ?? (inputs.url as string | undefined)
      if (url) lines.push(`${method} ${truncate(url, 22)}`)
      else lines.push(method)
      const auth = cfg.auth_type as string | undefined
      if (auth && auth !== "none") lines.push(`认证：${auth}`)
      break
    }

    case "code": {
      const lang = (cfg.language as string | undefined) ?? "python"
      lines.push(`语言：${lang}`)
      const code = cfg.code as string | undefined
      if (code?.trim()) {
        const firstLine = code.split("\n").find((l) => l.trim()) ?? ""
        if (firstLine) lines.push(truncate(firstLine.trim(), 26))
      }
      break
    }

    case "template": {
      const tpl = cfg.template as string | undefined
      if (tpl?.trim()) lines.push(`模板：${truncate(oneLine(tpl), 22)}`)
      break
    }

    case "iteration": {
      const blocks = Array.isArray(data.blocks) ? data.blocks.length : 0
      if (blocks > 0) lines.push(`子节点 × ${blocks}`)
      const itemVar = cfg.item_variable as string | undefined
      if (itemVar) lines.push(`项变量：${itemVar}`)
      break
    }

    case "variable-aggregator": {
      const groups = (cfg.groups as Array<{ name?: string; variables?: unknown[] }> | undefined) ?? []
      const total = groups.reduce((s, g) => s + (g.variables?.length ?? 0), 0)
      if (total > 0) lines.push(`聚合 × ${total}`)
      if (groups.length > 1) lines.push(`分组 × ${groups.length}`)
      break
    }

    case "variable-splitter": {
      const src = cfg.source_variable as string | undefined
      if (src) lines.push(`来源：${src}`)
      const keys = (cfg.keys as string[] | undefined) ?? []
      if (keys.length > 0) {
        lines.push(`拆出：${keys.slice(0, 3).join("、")}${keys.length > 3 ? "…" : ""}`)
      }
      break
    }

    case "human_approval": {
      const prompt = (cfg.prompt as string | undefined) ?? ""
      if (prompt.trim()) {
        lines.push(`提示：${truncate(oneLine(prompt), 22)}`)
      } else {
        lines.push("等待人工审批")
      }
      const approvers = (cfg.approvers as string[] | undefined) ?? []
      if (approvers.length > 0) {
        lines.push(`审批人：${approvers.slice(0, 2).join("、")}${approvers.length > 2 ? "…" : ""}`)
      }
      break
    }

    case "note":
      return null  // 便签不显示摘要（它自身就是内容）

    default: {
      // 未识别类型：显示已绑定的输入字段作为 fallback 提示。
      const boundKeys = Object.keys(inputs)
      if (boundKeys.length > 0) {
        lines.push(`输入：${boundKeys.slice(0, 3).join("、")}${boundKeys.length > 3 ? "…" : ""}`)
      }
    }
  }

  return lines.length > 0 ? lines : null
}


function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s
}


function oneLine(s: string): string {
  return s.replace(/\s+/g, " ").trim()
}
