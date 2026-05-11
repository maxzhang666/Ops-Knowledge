import { useNavigate } from "react-router-dom"
import { CheckCircle2, FileText, ListChecks, XCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { TimeDisplay } from "@/components/shared/time-display"
import type { ReviewItemView } from "@/api/review"
import { cn } from "@/lib/utils"

const UNIT_TYPE_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  document: FileText,
  entry: ListChecks,
}

const UNIT_TYPE_LABEL: Record<string, string> = {
  document: "文件",
  entry: "条目",
}

export function ReviewList({
  items,
  loading,
  emptyText,
  showActions,
  onApprove,
  onReject,
  onSelect,
  selectedId,
}: {
  items: ReviewItemView[]
  loading: boolean
  emptyText: string
  showActions: boolean
  onApprove?: (item: ReviewItemView) => void
  onReject?: (item: ReviewItemView) => void
  onSelect: (item: ReviewItemView) => void
  selectedId?: string | null
}) {
  const navigate = useNavigate()

  if (loading) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">加载中…</div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">{emptyText}</div>
    )
  }

  return (
    <div className="divide-y rounded-md border">
      {items.map((item) => {
        const Icon = UNIT_TYPE_ICON[item.unit_type] ?? FileText
        const typeLabel = UNIT_TYPE_LABEL[item.unit_type] ?? item.unit_type
        const isSelected = selectedId === item.unit_id
        return (
          <div
            key={`${item.unit_type}:${item.unit_id}`}
            className={cn(
              "flex items-center gap-3 px-3 py-2.5 text-sm hover:bg-muted/30 cursor-pointer",
              isSelected && "bg-muted/40",
            )}
            onClick={() => onSelect(item)}
          >
            <Icon className="size-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <Badge variant="outline" className="text-[10px]">
                  {typeLabel}
                </Badge>
                <span className="truncate font-medium">{item.title}</span>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                  onClick={(e) => {
                    e.stopPropagation()
                    navigate(`/knowledge/${item.kb_id}`)
                  }}
                >
                  · {item.kb_name}
                </button>
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                <span>提交人 {item.submitted_by.slice(0, 8)}</span>
                <span>·</span>
                <TimeDisplay value={item.submitted_at} />
                <span>·</span>
                <span>{item.chunk_count} 分块</span>
                {item.review_status === "approved" && (
                  <>
                    <span>·</span>
                    <span className="text-success">已通过</span>
                  </>
                )}
                {item.review_status === "rejected" && (
                  <>
                    <span>·</span>
                    <span className="text-destructive">已驳回</span>
                  </>
                )}
              </div>
            </div>
            {showActions && item.review_status === "pending" && (
              <div className="flex shrink-0 items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation()
                    onApprove?.(item)
                  }}
                >
                  <CheckCircle2 className="mr-1 size-3.5" /> 通过
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation()
                    onReject?.(item)
                  }}
                >
                  <XCircle className="mr-1 size-3.5" /> 驳回
                </Button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
