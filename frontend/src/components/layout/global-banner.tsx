import { AlertTriangle, Info, X, Gauge } from "lucide-react"

import { cn } from "@/lib/utils"
import { useBannerStore } from "@/stores/banner"

const kindStyle = {
  quota: {
    cls: "border-warning/40 bg-warning/10 text-warning-foreground",
    icon: Gauge,
  },
  warning: {
    cls: "border-warning/40 bg-warning/10 text-warning-foreground",
    icon: AlertTriangle,
  },
  info: {
    cls: "border-info/40 bg-info/10 text-info-foreground",
    icon: Info,
  },
} as const

export function GlobalBanner() {
  const banner = useBannerStore((s) => s.banner)
  const dismiss = useBannerStore((s) => s.dismiss)
  if (!banner) return null

  const { cls, icon: Icon } = kindStyle[banner.kind]
  return (
    <div className={cn("flex items-start gap-3 border-b px-4 py-2 text-sm", cls)}>
      <Icon className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{banner.title}</p>
        {banner.detail && <p className="text-xs opacity-80">{banner.detail}</p>}
      </div>
      <button
        type="button"
        onClick={dismiss}
        className="rounded p-1 hover:bg-background/40"
        title="关闭"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}
