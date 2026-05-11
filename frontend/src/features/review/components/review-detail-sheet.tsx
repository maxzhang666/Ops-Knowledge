import { CheckCircle2, MessageSquarePlus, XCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { TimeDisplay } from "@/components/shared/time-display"
import { DocumentPreview } from "@/features/knowledge/components/document-preview"
import type { ReviewItemView } from "@/api/review"

/** Plan 39 M3 — 审核详情 Sheet 抽屉。
 * 展示 unit 元信息 + chunks 切片情况 + 操作按钮。
 * 文件型 / 条目型未来可能展示不同内容预览。 */
export function ReviewDetailSheet({
  item,
  open,
  onOpenChange,
  onApprove,
  onReject,
  onComment,
}: {
  item: ReviewItemView | null
  open: boolean
  onOpenChange: (v: boolean) => void
  onApprove: (item: ReviewItemView) => void
  onReject: (item: ReviewItemView) => void
  onComment: (item: ReviewItemView) => void
}) {
  if (!item) return null

  const isPending = item.review_status === "pending"

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[640px] max-w-[80vw]">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Badge variant="outline">{item.unit_type === "document" ? "文件" : "条目"}</Badge>
            <span className="truncate">{item.title}</span>
          </SheetTitle>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          {/* 元信息 */}
          <div className="grid grid-cols-2 gap-3 rounded-md bg-muted/30 p-3 text-sm">
            <Metric label="知识库" value={item.kb_name} />
            <Metric label="切片数" value={`${item.chunk_count}`} />
            <Metric label="提交人" value={item.submitted_by.slice(0, 8)} />
            <Metric
              label="提交时间"
              value={<TimeDisplay value={item.submitted_at} />}
            />
            <Metric
              label="状态"
              value={
                <span
                  className={
                    item.review_status === "pending"
                      ? "text-warning"
                      : item.review_status === "approved"
                        ? "text-success"
                        : "text-destructive"
                  }
                >
                  {item.review_status === "pending"
                    ? "待审"
                    : item.review_status === "approved"
                      ? "已通过"
                      : "已驳回"}
                </span>
              }
            />
            {item.reviewed_at && (
              <Metric label="审核时间" value={<TimeDisplay value={item.reviewed_at} />} />
            )}
          </div>

          {/* 评论 / 驳回理由 */}
          {item.review_comment && (
            <div className="rounded-md border border-border/60 bg-muted/20 p-3">
              <div className="mb-1 text-xs font-medium text-muted-foreground">
                {item.review_status === "rejected" ? "驳回理由" : "审核反馈"}
              </div>
              <div className="whitespace-pre-wrap text-sm">{item.review_comment}</div>
            </div>
          )}

          {/* 切片提示 */}
          {item.chunk_count === 0 && (
            <div className="rounded-md border border-warning/40 bg-warning/5 p-3 text-xs text-warning">
              ⏳ 切片中... 切片完成后内容才能进入向量库。可以现在审核，切片完成时会自动跟随状态。
            </div>
          )}

          {/* 内容预览 */}
          <div className="rounded-md border bg-background overflow-hidden" style={{ height: 360 }}>
            {item.unit_type === "document" && item.file_source_type ? (
              <DocumentPreview
                kbId={item.kb_id}
                docId={item.unit_id}
                sourceType={item.file_source_type}
                title={item.title}
              />
            ) : item.unit_type === "entry" ? (
              <div className="p-4 text-xs text-muted-foreground">条目内容预览（Plan 41 接入）</div>
            ) : (
              <div className="p-4 text-xs text-muted-foreground">该类型暂不支持预览</div>
            )}
          </div>

          {/* 操作 */}
          {isPending && (
            <div className="flex items-center justify-end gap-2 border-t pt-4">
              <Button
                variant="outline"
                onClick={() => onComment(item)}
              >
                <MessageSquarePlus className="mr-1.5 size-4" /> 评论
              </Button>
              <Button
                variant="outline"
                className="text-destructive hover:text-destructive"
                onClick={() => onReject(item)}
              >
                <XCircle className="mr-1.5 size-4" /> 驳回
              </Button>
              <Button onClick={() => onApprove(item)}>
                <CheckCircle2 className="mr-1.5 size-4" /> 通过
              </Button>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
