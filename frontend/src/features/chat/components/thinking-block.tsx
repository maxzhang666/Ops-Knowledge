import { useState } from "react"
import { ChevronDown, ChevronRight, Brain } from "lucide-react"
import { cn } from "@/lib/utils"

interface ThinkingBlockProps {
  steps: string[]
}

export function ThinkingBlock({ steps }: ThinkingBlockProps) {
  const [open, setOpen] = useState(false)

  if (steps.length === 0) return null

  return (
    <div className="mb-2 rounded-lg border bg-muted/30 text-xs">
      <button
        className="flex w-full items-center gap-2 px-3 py-2 text-muted-foreground hover:text-foreground"
        onClick={() => setOpen(!open)}
      >
        <Brain className="size-3.5" />
        <span>思维链 ({steps.length} 步)</span>
        {open ? <ChevronDown className="ml-auto size-3.5" /> : <ChevronRight className="ml-auto size-3.5" />}
      </button>
      <div className={cn("overflow-hidden transition-all", open ? "max-h-96 overflow-y-auto" : "max-h-0")}>
        <div className="space-y-1 px-3 pb-2">
          {steps.map((step, i) => (
            <p key={i} className="text-muted-foreground">{step}</p>
          ))}
        </div>
      </div>
    </div>
  )
}
