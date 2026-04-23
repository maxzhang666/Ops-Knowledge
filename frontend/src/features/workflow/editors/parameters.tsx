import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"

/**
 * Parameter Extractor `parameters: [{name, type, description?, required?}]`
 * — array-of-object, one row per extracted field.
 */

const PARAM_TYPES = ["string", "number", "boolean", "array"] as const
type ParamType = (typeof PARAM_TYPES)[number]

interface Param {
  name: string
  type: ParamType
  description?: string
  required?: boolean
}

export function ParametersEditor({
  value,
  onChange,
}: {
  value: Param[] | undefined
  onChange: (next: Param[]) => void
}) {
  const items = value ?? []

  function update(idx: number, patch: Partial<Param>) {
    onChange(items.map((p, i) => (i === idx ? { ...p, ...patch } : p)))
  }

  function remove(idx: number) {
    onChange(items.filter((_, i) => i !== idx))
  }

  function add() {
    onChange([...items, { name: "", type: "string", description: "", required: false }])
  }

  return (
    <div className="space-y-2">
      {items.map((p, idx) => (
        <div key={idx} className="rounded-md border p-2 text-xs">
          <div className="mb-1 flex gap-1">
            <Input
              value={p.name}
              onChange={(e) => update(idx, { name: e.target.value })}
              placeholder="字段名"
              className="h-7 flex-1 text-xs"
            />
            <select
              value={p.type}
              onChange={(e) => update(idx, { type: e.target.value as ParamType })}
              className="h-7 rounded-md border border-input bg-background px-2 text-xs"
            >
              {PARAM_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <label className="flex items-center gap-1.5">
              <Switch
                checked={Boolean(p.required)}
                onCheckedChange={(b) => update(idx, { required: b })}
              />
              <span>必填</span>
            </label>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => remove(idx)}
            >
              <Trash2 className="size-3.5 text-destructive" />
            </Button>
          </div>
          <Input
            value={p.description ?? ""}
            onChange={(e) => update(idx, { description: e.target.value })}
            placeholder="描述（用于指导 LLM 提取）"
            className="h-7 text-xs"
          />
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add}>
        <Plus className="mr-1 size-3.5" /> 添加参数
      </Button>
    </div>
  )
}
