import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"

/**
 * Editor for Start node `variables: [{name, type, required?, default?}]`.
 * This defines the typed input contract for the workflow (and therefore for
 * the Workflow Agent's chat entry).
 */

const VAR_TYPES = ["string", "number", "boolean", "object", "array"] as const
type VarType = (typeof VAR_TYPES)[number]

interface Variable {
  name: string
  type: VarType
  required?: boolean
  default?: unknown
}

export function VariablesEditor({
  value,
  onChange,
}: {
  value: Variable[] | undefined
  onChange: (next: Variable[]) => void
}) {
  const items = value ?? []

  function update(idx: number, patch: Partial<Variable>) {
    onChange(items.map((v, i) => (i === idx ? { ...v, ...patch } : v)))
  }

  function remove(idx: number) {
    onChange(items.filter((_, i) => i !== idx))
  }

  function add() {
    onChange([...items, { name: "", type: "string", required: false }])
  }

  return (
    <div className="space-y-2">
      {items.length === 0 && (
        <p className="text-xs text-muted-foreground">
          未定义输入变量 — Start 节点会透传 trigger_input
        </p>
      )}
      {items.map((v, idx) => (
        <div key={idx} className="rounded-md border p-2 text-xs">
          <div className="mb-1 flex gap-1">
            <Input
              value={v.name}
              onChange={(e) => update(idx, { name: e.target.value })}
              placeholder="变量名 (标识符)"
              className="h-7 flex-1 text-xs"
            />
            <select
              value={v.type}
              onChange={(e) => update(idx, { type: e.target.value as VarType })}
              className="h-7 rounded-md border border-input bg-background px-2 text-xs"
            >
              {VAR_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => remove(idx)}
            >
              <Trash2 className="size-3.5 text-destructive" />
            </Button>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5">
              <Switch
                checked={Boolean(v.required)}
                onCheckedChange={(b) => update(idx, { required: b })}
              />
              <span>必填</span>
            </label>
            <Input
              value={toDisplay(v.default)}
              onChange={(e) => update(idx, { default: fromDisplay(e.target.value, v.type) })}
              placeholder="默认值（可选）"
              className="h-7 flex-1 text-xs"
              disabled={Boolean(v.required)}
            />
          </div>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add}>
        <Plus className="mr-1 size-3.5" /> 添加变量
      </Button>
    </div>
  )
}


function toDisplay(v: unknown): string {
  if (v === undefined || v === null) return ""
  if (typeof v === "string") return v
  return JSON.stringify(v)
}

function fromDisplay(s: string, t: VarType): unknown {
  if (s === "") return undefined
  if (t === "string") return s
  if (t === "boolean") return s === "true" || s === "1"
  if (t === "number") {
    const n = Number(s)
    return Number.isFinite(n) ? n : s
  }
  try {
    return JSON.parse(s)
  } catch {
    return s
  }
}
