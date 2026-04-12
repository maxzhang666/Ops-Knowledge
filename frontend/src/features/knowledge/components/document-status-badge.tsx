import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { DocumentStatus } from "@/api/knowledge"

const statusConfig: Record<DocumentStatus, { label: string; className: string }> = {
  pending: { label: "等待中", className: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300" },
  processing: { label: "处理中", className: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300" },
  completed: { label: "已完成", className: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300" },
  error: { label: "失败", className: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300" },
}

interface DocumentStatusBadgeProps {
  status: DocumentStatus
}

export function DocumentStatusBadge({ status }: DocumentStatusBadgeProps) {
  const config = statusConfig[status]
  return (
    <Badge variant="outline" className={cn("border-transparent", config.className)}>
      {status === "processing" && (
        <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {config.label}
    </Badge>
  )
}
