import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/**
 * Generic key→value editor for simple string-to-string object fields:
 *   HTTP Request.headers  — request headers
 *   HTTP Request.params   — query string
 *   Variable Splitter.mapping — output-name → source path
 *
 * Both sides are free text. Values can reference workflow variables via
 * `{{#node.field#}}` since backend template resolution also runs on string
 * config values before passing to the node.
 */

type Entry = [string, string]


export function KeyValueEditor({
  value,
  onChange,
  keyPlaceholder = "key",
  valuePlaceholder = "value",
}: {
  value: Record<string, unknown> | undefined
  onChange: (next: Record<string, string>) => void
  keyPlaceholder?: string
  valuePlaceholder?: string
}) {
  // Convert the object into an ordered list of tuples so renaming a key mid-
  // edit doesn't wipe the row.
  const entries: Entry[] = Object.entries(value ?? {}).map(([k, v]) => [
    k,
    typeof v === "string" ? v : JSON.stringify(v),
  ])

  function emit(next: Entry[]) {
    const out: Record<string, string> = {}
    for (const [k, v] of next) {
      if (k) out[k] = v
    }
    onChange(out)
  }

  function update(idx: number, key: string, val: string) {
    const next = entries.slice()
    next[idx] = [key, val]
    emit(next)
  }

  function remove(idx: number) {
    emit(entries.filter((_, i) => i !== idx))
  }

  function add() {
    emit([...entries, ["", ""]])
  }

  return (
    <div className="space-y-1">
      {entries.length === 0 && (
        <p className="text-xs text-muted-foreground">（空）</p>
      )}
      {entries.map((e, idx) => (
        <div key={idx} className="flex gap-1">
          <Input
            value={e[0]}
            onChange={(ev) => update(idx, ev.target.value, e[1])}
            placeholder={keyPlaceholder}
            className="h-7 flex-1 text-xs"
          />
          <Input
            value={e[1]}
            onChange={(ev) => update(idx, e[0], ev.target.value)}
            placeholder={valuePlaceholder}
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
        <Plus className="mr-1 size-3.5" /> 添加
      </Button>
    </div>
  )
}
