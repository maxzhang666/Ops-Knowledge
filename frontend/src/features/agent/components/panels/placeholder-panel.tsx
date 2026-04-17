import { Construction } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { MenuItem } from "../agent-menu"

interface PlaceholderPanelProps {
  item: MenuItem
}

export function PlaceholderPanel({ item }: PlaceholderPanelProps) {
  const Icon = item.icon
  const phaseLabel = item.phase === "1b" ? "Phase 1b" : `Phase ${item.phase}`

  return (
    <div className="flex h-full items-center justify-center p-10">
      <div className="flex max-w-md flex-col items-center gap-5 text-center">
        <div className="relative">
          <div className="flex size-20 items-center justify-center rounded-2xl bg-muted">
            <Icon className="size-10 text-muted-foreground" />
          </div>
          <div className="absolute -bottom-1 -right-1 flex size-7 items-center justify-center rounded-full bg-background shadow">
            <Construction className="size-3.5 text-amber-500" />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-center gap-2">
            <h3 className="text-base font-semibold">{item.label}</h3>
            <Badge variant="secondary" className="text-[10px]">即将开放</Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {item.description || "该能力正在规划中，敬请期待。"}
          </p>
          <div className="text-[10px] text-muted-foreground">
            预计发布版本：<span className="font-medium">{phaseLabel}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
