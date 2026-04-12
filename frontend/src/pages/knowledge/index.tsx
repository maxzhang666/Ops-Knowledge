import { useCallback, useEffect, useState } from "react"
import { BookOpen, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/shared/empty-state"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { KBCard } from "@/features/knowledge/components/kb-card"
import { KBCreateDialog } from "@/features/knowledge/components/kb-create-dialog"
import { knowledgeApi, type KnowledgeBase } from "@/api/knowledge"

export default function KnowledgePage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)

  const loadKBs = useCallback(async () => {
    setLoading(true)
    try {
      const res = await knowledgeApi.listKBs()
      setKbs(res.items)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadKBs()
  }, [loadKBs])

  if (loading) {
    return <LoadingSpinner className="py-32" size="lg" />
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold">知识库</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 size-4" />
          创建
        </Button>
      </div>

      {kbs.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="h-12 w-12" />}
          title="暂无知识库"
          description="创建你的第一个知识库来开始管理文档"
          action={{ label: "创建知识库", onClick: () => setCreateOpen(true) }}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {kbs.map((kb) => (
            <KBCard key={kb.id} kb={kb} />
          ))}
        </div>
      )}

      <KBCreateDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={loadKBs} />
    </div>
  )
}
