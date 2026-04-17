import { useCallback, useEffect, useRef, useState } from "react"
import { BookOpen, Plus, Upload } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/shared/empty-state"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { KBCard } from "@/features/knowledge/components/kb-card"
import { KBCreateDialog } from "@/features/knowledge/components/kb-create-dialog"
import { knowledgeApi, type KnowledgeBase } from "@/api/knowledge"

export default function KnowledgePage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeBase | null>(null)
  const [importing, setImporting] = useState(false)
  const importInputRef = useRef<HTMLInputElement>(null)

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

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await knowledgeApi.deleteKB(deleteTarget.id)
      toast.success(`已删除 "${deleteTarget.name}"`)
      setDeleteTarget(null)
      loadKBs()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.endsWith(".oka")) {
      toast.error("仅支持 .oka 格式")
      if (importInputRef.current) importInputRef.current.value = ""
      return
    }
    setImporting(true)
    try {
      const fd = new FormData()
      fd.append("file", file)
      await knowledgeApi.importKB(fd)
      toast.success(`已导入 ${file.name}`)
      loadKBs()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "导入失败")
    } finally {
      setImporting(false)
      if (importInputRef.current) importInputRef.current.value = ""
    }
  }

  if (loading) {
    return <LoadingSpinner className="py-32" size="lg" />
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold">知识库</h1>
        <div className="flex items-center gap-2">
          <input
            ref={importInputRef}
            type="file"
            accept=".oka"
            className="hidden"
            onChange={handleImportFile}
          />
          <Button
            variant="outline"
            disabled={importing}
            onClick={() => importInputRef.current?.click()}
          >
            <Upload className="mr-1 size-4" />
            {importing ? "导入中..." : "导入 .oka"}
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1 size-4" />
            创建
          </Button>
        </div>
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
            <KBCard key={kb.id} kb={kb} onDelete={setDeleteTarget} />
          ))}
        </div>
      )}

      <KBCreateDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={loadKBs} />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title={`删除知识库 "${deleteTarget?.name ?? ""}"`}
        description="此操作将永久删除该知识库及其所有文档、切片、向量数据，无法恢复。请输入知识库名称以确认。"
        confirmText="永久删除"
        typeToConfirm={deleteTarget?.name}
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}
