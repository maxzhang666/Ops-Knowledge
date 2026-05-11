import { Badge } from "@/components/ui/badge"
import type { DocumentStatus } from "@/api/knowledge"

type BadgeVariant = "secondary" | "info" | "success" | "destructive"

const statusConfig: Record<DocumentStatus, { label: string; variant: BadgeVariant }> = {
  pending:    { label: "等待中", variant: "secondary" },
  processing: { label: "处理中", variant: "info" },
  completed:  { label: "已完成", variant: "success" },
  error:      { label: "失败",   variant: "destructive" },
}

interface DocumentStatusBadgeProps {
  status: DocumentStatus
  className?: string
}

export function DocumentStatusBadge({ status, className }: DocumentStatusBadgeProps) {
  const config = statusConfig[status]
  return (
    <Badge variant={config.variant} className={className}>
      {status === "processing" && (
        <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {config.label}
    </Badge>
  )
}
