import { useMemo, useState } from "react"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { useEditorStore } from "../store"
import { computeUpstream, type VariableSource } from "../variable-editor/upstream"
import { VariableEditor } from "../variable-editor/editor"


/**
 * Bind a declared node input (`io.inputs[<name>]`) to either:
 *  - a selector into an upstream node / workflow vars, stored as `[id, field]`
 *  - a literal value, stored as a raw JS value matching the declared type
 *
 * Template mode (`"text {{#node.field#}}"`) is reachable via the workflow's
 * VariableEditor for string-typed inputs like Answer.answer / Template.template
 * already — this editor covers the structured case most nodes need.
 */
interface Props {
  name: string
  schema: { type?: string }
  value: unknown
  onChange: (v: unknown) => void
  currentNodeId: string
}


export function InputBindingEditor({ name, schema, value, onChange, currentNodeId }: Props) {
  const nodes = useEditorStore((s) => s.nodes)
  const edges = useEditorStore((s) => s.edges)
  const catalog = useEditorStore((s) => s.catalog)

  const sources = useMemo(
    () => computeUpstream(currentNodeId, nodes, edges, catalog, []),
    [currentNodeId, nodes, edges, catalog],
  )
  const options = useMemo(() => flatten(sources), [sources])

  const isSelector = Array.isArray(value) && value.length >= 2
  const isTemplateString =
    typeof value === "string" && /\{\{#.+?#\}\}/.test(value)

  const [mode, setMode] = useState<"selector" | "template" | "literal">(() => {
    if (isSelector) return "selector"
    if (isTemplateString) return "template"
    if (value !== undefined && value !== null) return "literal"
    return "selector"
  })

  const selectorKey = isSelector
    ? (value as string[]).join(".")
    : ""

  function onPickSelector(key: string) {
    if (!key) {
      onChange(undefined)
      return
    }
    const parts = key.split(".")
    onChange(parts)
  }

  function onLiteralChange(raw: string) {
    if (raw === "") {
      onChange(undefined)
      return
    }
    const t = schema.type
    if (t === "number" || t === "integer") {
      const n = Number(raw)
      onChange(Number.isFinite(n) ? n : raw)
      return
    }
    if (t === "boolean") {
      onChange(raw === "true" || raw === "1")
      return
    }
    onChange(raw)
  }

  return (
    <div className="flex flex-col gap-1 rounded-md border bg-muted/20 p-2">
      <div className="flex items-center justify-between">
        <Label className="text-xs">
          {name}
          {schema.type && (
            <span className="ml-1 text-muted-foreground">({schema.type as string})</span>
          )}
        </Label>
        <div className="flex gap-1">
          <ModeButton active={mode === "selector"} onClick={() => setMode("selector")}>
            变量
          </ModeButton>
          <ModeButton active={mode === "template"} onClick={() => setMode("template")}>
            模板
          </ModeButton>
          <ModeButton active={mode === "literal"} onClick={() => setMode("literal")}>
            字面值
          </ModeButton>
        </div>
      </div>

      {mode === "selector" && (
        options.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">
            当前节点无上游 — 需要先拖入节点并连线
          </p>
        ) : (
          <select
            value={selectorKey}
            onChange={(e) => onPickSelector(e.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
          >
            <option value="">(未绑定)</option>
            {options.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
        )
      )}

      {mode === "template" && (
        <VariableEditor
          value={typeof value === "string" ? value : ""}
          onChange={(v) => onChange(v)}
          currentNodeId={currentNodeId}
          placeholder="混合文本与变量，{{ 或 / 插入"
        />
      )}

      {mode === "literal" && (
        <Input
          value={isSelector || isTemplateString ? "" : (value as string | undefined) ?? ""}
          onChange={(e) => onLiteralChange(e.target.value)}
          placeholder={schema.type === "number" ? "数字字面值" : "文本字面值"}
          className="h-8 text-xs"
        />
      )}
    </div>
  )
}


function ModeButton({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded px-1.5 text-[10px] ${
        active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
      }`}
    >
      {children}
    </button>
  )
}


interface Option {
  key: string         // e.g. "llm_abc.content" or "vars.trigger.query"
  label: string       // human-friendly — "LLM Call.content"
  type: string
}


function flatten(sources: VariableSource[]): Option[] {
  const out: Option[] = []
  for (const s of sources) {
    for (const f of s.fields) {
      // Sub-paths (vars.trigger has nested fields we don't know at author
      // time). We emit the top level only; users can drill via literal edit
      // for now — nested drilldown is a future enhancement.
      const key = `${s.node_id}.${f.name}`
      const label = `${s.label}.${f.name}`
      out.push({ key, label, type: f.type })
    }
  }
  return out
}
