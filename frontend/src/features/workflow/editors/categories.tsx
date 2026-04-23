import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/**
 * Edits arrays of `{id, name, description}` — used by Question Classifier's
 * categories config. The exact same shape is reused by Parameter Extractor's
 * `parameters` when we eventually ship a similar editor.
 */

interface Category {
  id: string
  name: string
  description?: string
}

export function CategoriesEditor({
  value,
  onChange,
}: {
  value: Category[] | undefined
  onChange: (next: Category[]) => void
}) {
  const items = value ?? []

  function update(idx: number, patch: Partial<Category>) {
    onChange(items.map((c, i) => (i === idx ? { ...c, ...patch } : c)))
  }
  function remove(idx: number) {
    onChange(items.filter((_, i) => i !== idx))
  }
  function add() {
    onChange([...items, { id: `cat_${items.length + 1}`, name: "", description: "" }])
  }

  return (
    <div className="space-y-2">
      {items.map((c, idx) => (
        <div key={idx} className="flex gap-1">
          <Input
            value={c.id}
            onChange={(e) => update(idx, { id: e.target.value })}
            placeholder="id"
            className="h-7 w-20 text-xs"
          />
          <Input
            value={c.name}
            onChange={(e) => update(idx, { name: e.target.value })}
            placeholder="名称"
            className="h-7 flex-1 text-xs"
          />
          <Input
            value={c.description ?? ""}
            onChange={(e) => update(idx, { description: e.target.value })}
            placeholder="描述（帮助 LLM 判断）"
            className="h-7 flex-1 text-xs"
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => remove(idx)}
          >
            <Trash2 className="size-3.5 text-destructive" />
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add}>
        <Plus className="mr-1 size-3.5" /> 添加分类
      </Button>
    </div>
  )
}
