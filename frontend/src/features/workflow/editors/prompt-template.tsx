import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { VariableEditor } from "../variable-editor/editor"

interface Msg {
  role: "system" | "user" | "assistant"
  text: string
}

/**
 * LLM node's `prompt_template: [{role, text}]` — the text field is variable-
 * aware so we wrap with TipTap. Role is a fixed 3-choice select.
 */
export function PromptTemplateEditor({
  value,
  onChange,
  currentNodeId,
}: {
  value: Msg[] | undefined
  onChange: (next: Msg[]) => void
  currentNodeId: string
}) {
  const items = value ?? []

  function update(idx: number, patch: Partial<Msg>) {
    onChange(items.map((m, i) => (i === idx ? { ...m, ...patch } : m)))
  }
  function remove(idx: number) {
    onChange(items.filter((_, i) => i !== idx))
  }
  function add() {
    onChange([...items, { role: "user", text: "" }])
  }

  return (
    <div className="space-y-3">
      {items.map((m, idx) => (
        <div key={idx} className="rounded-md border p-2">
          <div className="mb-1 flex items-center justify-between">
            <select
              value={m.role}
              onChange={(e) =>
                update(idx, { role: e.target.value as Msg["role"] })
              }
              className="h-7 rounded-md border border-input bg-background px-2 text-xs"
            >
              <option value="system">system</option>
              <option value="user">user</option>
              <option value="assistant">assistant</option>
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
          <VariableEditor
            value={m.text}
            onChange={(v) => update(idx, { text: v })}
            currentNodeId={currentNodeId}
            placeholder="消息内容 — {{ 或 / 插入变量"
          />
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add}>
        <Plus className="mr-1 size-3.5" /> 添加消息
      </Button>
    </div>
  )
}
