import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { ReviewList } from "@/features/review/components/review-list"
import { ReviewDetailSheet } from "@/features/review/components/review-detail-sheet"
import { RejectDialog } from "@/features/review/components/reject-dialog"
import { reviewApi, type ReviewItemView } from "@/api/review"
import type { KnowledgeBase } from "@/api/knowledge"

/** Plan 39 M4.1 — KB 详情「审批」tab。
 * 复用全局审核中心的 ReviewList / DetailSheet / RejectDialog 组件，
 * 仅按 kb_id 过滤；UX 与 /review 全局工作台一致。 */
export function ReviewTab({
  kb,
  onPick,
}: {
  kb: KnowledgeBase
  /** 选中条目时同步 documents tab 的选中状态（让用户看完 Sheet 后切回 documents 直接对位） */
  onPick: (docId: string) => void
}) {
  const [items, setItems] = useState<ReviewItemView[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<ReviewItemView | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [rejectTarget, setRejectTarget] = useState<ReviewItemView | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await reviewApi.listPending({ kb_id: kb.id, page_size: 50 })
      setItems(r.items)
    } finally {
      setLoading(false)
    }
  }, [kb.id])

  useEffect(() => { load() }, [load])

  async function handleApprove(item: ReviewItemView) {
    try {
      await reviewApi.approve(item.unit_type, item.unit_id)
      toast.success(`已通过：${item.title}`)
      setSheetOpen(false)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "审核失败")
    }
  }

  async function handleReject(comment: string) {
    if (!rejectTarget) return
    try {
      await reviewApi.reject(rejectTarget.unit_type, rejectTarget.unit_id, comment)
      toast.success(`已驳回：${rejectTarget.title}`)
      setSheetOpen(false)
      setRejectTarget(null)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "驳回失败")
    }
  }

  async function handleComment(item: ReviewItemView) {
    const text = window.prompt("输入评论建议：")
    if (!text || !text.trim()) return
    try {
      await reviewApi.comment(item.unit_type, item.unit_id, text.trim())
      toast.success("评论已发送给作者")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "评论失败")
    }
  }

  return (
    <div className="space-y-2">
      <span className="text-sm font-medium">待审 ({items.length})</span>

      <ReviewList
        items={items}
        loading={loading}
        emptyText="该知识库当前没有待审项"
        showActions
        onApprove={handleApprove}
        onReject={(item) => setRejectTarget(item)}
        onSelect={(item) => {
          setSelected(item)
          setSheetOpen(true)
          // 同步 documents tab 选中状态（用户关闭 Sheet 切到 documents 时已选好）
          if (item.unit_type === "document") {
            onPick(item.unit_id)
          }
        }}
        selectedId={selected?.unit_id ?? null}
      />

      <ReviewDetailSheet
        item={selected}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        onApprove={handleApprove}
        onReject={(item) => setRejectTarget(item)}
        onComment={handleComment}
      />

      <RejectDialog
        open={!!rejectTarget}
        onOpenChange={(v) => { if (!v) setRejectTarget(null) }}
        unitTitle={rejectTarget?.title ?? ""}
        onConfirm={handleReject}
      />
    </div>
  )
}
