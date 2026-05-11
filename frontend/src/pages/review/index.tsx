import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ReviewList } from "@/features/review/components/review-list"
import { ReviewDetailSheet } from "@/features/review/components/review-detail-sheet"
import { RejectDialog } from "@/features/review/components/reject-dialog"
import { reviewApi, type ReviewItemView } from "@/api/review"

type TabKey = "pending" | "reviewed_by_me" | "submitted_by_me"

const TAB_LABEL: Record<TabKey, string> = {
  pending: "待审",
  reviewed_by_me: "我审过",
  submitted_by_me: "我提交的",
}

export default function ReviewCenterPage() {
  const [tab, setTab] = useState<TabKey>("pending")
  const [pending, setPending] = useState<ReviewItemView[]>([])
  const [history, setHistory] = useState<ReviewItemView[]>([])
  const [loading, setLoading] = useState(true)
  const [pendingCount, setPendingCount] = useState(0)

  const [selected, setSelected] = useState<ReviewItemView | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [rejectTarget, setRejectTarget] = useState<ReviewItemView | null>(null)

  const loadPending = useCallback(async () => {
    setLoading(true)
    try {
      const r = await reviewApi.listPending({ page_size: 50 })
      setPending(r.items)
      setPendingCount(r.total)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadHistory = useCallback(async (mode: "reviewed_by_me" | "submitted_by_me") => {
    setLoading(true)
    try {
      const r = await reviewApi.listHistory(mode, 1, 50)
      setHistory(r.items)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (tab === "pending") loadPending()
    else loadHistory(tab)
  }, [tab, loadPending, loadHistory])

  function openDetail(item: ReviewItemView) {
    setSelected(item)
    setSheetOpen(true)
  }

  async function handleApprove(item: ReviewItemView) {
    try {
      await reviewApi.approve(item.unit_type, item.unit_id)
      toast.success(`已通过：${item.title}`)
      setSheetOpen(false)
      loadPending()
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
      loadPending()
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
      loadPending()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "评论失败")
    }
  }

  return (
    <div className="mx-auto max-w-[1100px] p-6">
      <h1 className="mb-4 text-xl font-semibold">审核中心</h1>

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <TabsList>
          <TabsTrigger value="pending">
            {TAB_LABEL.pending}
            {pendingCount > 0 && (
              <span className="ml-1 rounded-full bg-destructive px-1.5 text-[10px] font-medium text-destructive-foreground">
                {pendingCount}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="reviewed_by_me">{TAB_LABEL.reviewed_by_me}</TabsTrigger>
          <TabsTrigger value="submitted_by_me">{TAB_LABEL.submitted_by_me}</TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="mt-3">
          <ReviewList
            items={pending}
            loading={loading}
            emptyText="当前没有待审项"
            showActions
            onApprove={handleApprove}
            onReject={(item) => {
              setRejectTarget(item)
            }}
            onSelect={openDetail}
            selectedId={selected?.unit_id ?? null}
          />
        </TabsContent>

        <TabsContent value="reviewed_by_me" className="mt-3">
          <ReviewList
            items={history}
            loading={loading}
            emptyText="尚未审核过任何内容"
            showActions={false}
            onSelect={openDetail}
          />
        </TabsContent>

        <TabsContent value="submitted_by_me" className="mt-3">
          <ReviewList
            items={history}
            loading={loading}
            emptyText="尚未提交过待审内容"
            showActions={false}
            onSelect={openDetail}
          />
        </TabsContent>
      </Tabs>

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
