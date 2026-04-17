import { useCallback, useEffect, useState } from "react"
import { Bot, Plus } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/shared/empty-state"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { AgentCard } from "@/features/agent/components/agent-card"
import { AgentCreateDialog } from "@/features/agent/components/agent-create-dialog"
import { agentApi, type Agent } from "@/api/agent"

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Agent | null>(null)

  const loadAgents = useCallback(async () => {
    setLoading(true)
    try {
      const res = await agentApi.list()
      setAgents(res.items)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAgents()
  }, [loadAgents])

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await agentApi.delete(deleteTarget.id)
      toast.success(`已删除 "${deleteTarget.name}"`)
      setDeleteTarget(null)
      loadAgents()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  if (loading) {
    return <LoadingSpinner className="py-32" size="lg" />
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold">智能体</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 size-4" />
          创建
        </Button>
      </div>

      {agents.length === 0 ? (
        <EmptyState
          icon={<Bot className="h-12 w-12" />}
          title="暂无智能体"
          description="创建你的第一个智能体来开始对话"
          action={{ label: "创建智能体", onClick: () => setCreateOpen(true) }}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} onDelete={setDeleteTarget} />
          ))}
        </div>
      )}

      <AgentCreateDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={loadAgents} />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title={`删除智能体 "${deleteTarget?.name ?? ""}"`}
        description="此操作将永久删除该智能体及其所有会话历史，无法恢复。请输入智能体名称以确认。"
        confirmText="永久删除"
        typeToConfirm={deleteTarget?.name}
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}
