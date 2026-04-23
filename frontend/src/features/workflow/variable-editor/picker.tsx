import { useEffect, useState } from "react"
import type { VariableSource } from "./upstream"

interface Props {
  sources: VariableSource[]
  onPick: (nodeId: string, field: string) => void
  onClose: () => void
  position: { top: number; left: number }
  query?: string
}

interface Row {
  source: VariableSource
  field: string
  type: string
}


export function VariablePicker({ sources, onPick, onClose, position, query = "" }: Props) {
  const [focusIdx, setFocusIdx] = useState(0)
  const items = flatten(sources, query)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return }
      if (e.key === "ArrowDown") {
        setFocusIdx((i) => Math.min(i + 1, items.length - 1))
        e.preventDefault()
      } else if (e.key === "ArrowUp") {
        setFocusIdx((i) => Math.max(i - 1, 0))
        e.preventDefault()
      } else if (e.key === "Enter") {
        const cur = items[focusIdx]
        if (cur) onPick(cur.source.node_id, cur.field)
        e.preventDefault()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [focusIdx, items, onPick, onClose])

  return (
    <div
      className="z-50 max-h-64 w-72 overflow-y-auto rounded-md border bg-popover p-1 shadow-md"
      style={{ position: "fixed", top: position.top, left: position.left }}
    >
      {items.length === 0 ? (
        <div className="px-2 py-1 text-xs text-muted-foreground">无可用变量</div>
      ) : (
        items.map((it, i) => (
          <button
            key={`${it.source.node_id}.${it.field}`}
            type="button"
            className={`flex w-full items-center justify-between rounded px-2 py-1 text-xs hover:bg-muted ${
              i === focusIdx ? "bg-muted" : ""
            }`}
            onClick={() => onPick(it.source.node_id, it.field)}
            onMouseEnter={() => setFocusIdx(i)}
          >
            <span className="truncate">
              <span className="font-medium">{it.source.label}</span>
              <span className="text-muted-foreground">.{it.field}</span>
            </span>
            <span className="text-muted-foreground">{it.type}</span>
          </button>
        ))
      )}
    </div>
  )
}


function flatten(sources: VariableSource[], query: string): Row[] {
  const out: Row[] = []
  const q = query.toLowerCase()
  for (const s of sources) {
    for (const f of s.fields) {
      if (
        !q ||
        f.name.toLowerCase().includes(q) ||
        s.label.toLowerCase().includes(q)
      ) {
        out.push({ source: s, field: f.name, type: f.type })
      }
    }
  }
  return out
}
