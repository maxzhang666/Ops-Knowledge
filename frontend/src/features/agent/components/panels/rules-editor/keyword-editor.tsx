import { useState } from "react"
import { Plus, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"

interface Props {
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
}

export function KeywordEditor({ value, onChange }: Props) {
  const list = (value.any_of as string[]) ?? []
  const caseSensitive = (value.case_sensitive as boolean) ?? false
  const [draft, setDraft] = useState("")

  function add() {
    const v = draft.trim()
    if (!v || list.includes(v)) { setDraft(""); return }
    onChange({ ...value, any_of: [...list, v] })
    setDraft("")
  }

  function remove(i: number) {
    onChange({ ...value, any_of: list.filter((_, idx) => idx !== i) })
  }

  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <Label className="text-[11px]">关键词（任一命中即匹配）</Label>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {list.map((kw, i) => (
          <Badge key={kw} variant="secondary" className="gap-1 pr-1 text-xs">
            {kw}
            <button type="button" onClick={() => remove(i)} className="ml-0.5 hover:text-destructive">
              <X className="size-3" />
            </button>
          </Badge>
        ))}
        <div className="flex items-center gap-1">
          <Input
            className="h-7 w-32 text-xs"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add() } }}
            placeholder="输入 + 回车"
          />
          <button
            type="button"
            onClick={add}
            className="inline-flex size-7 items-center justify-center rounded hover:bg-accent"
          >
            <Plus className="size-3.5" />
          </button>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2 text-xs">
        <Switch
          checked={caseSensitive}
          onCheckedChange={(v) => onChange({ ...value, case_sensitive: v })}
        />
        <span>大小写敏感</span>
      </div>
    </div>
  )
}
