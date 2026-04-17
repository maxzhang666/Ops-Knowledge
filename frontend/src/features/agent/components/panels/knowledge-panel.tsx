import { useCallback, useEffect, useState } from "react"
import { X, Check } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

import { agentApi, type Agent } from "@/api/agent"
import { knowledgeApi, type KnowledgeBase } from "@/api/knowledge"

interface KnowledgePanelProps {
  agent: Agent
  onUpdated: () => void
}

export function KnowledgePanel({ agent, onUpdated }: KnowledgePanelProps) {
  const [allKBs, setAllKBs] = useState<KnowledgeBase[]>([])
  const [kbIds, setKbIds] = useState<string[]>(agent.knowledge_base_ids ?? [])
  const [topK, setTopK] = useState<number>(
    (agent.retrieval_config?.top_k as number | undefined) ?? 5,
  )
  const [rewrite, setRewrite] = useState<boolean>(
    (agent.retrieval_config?.rewrite as boolean | undefined) ?? false,
  )
  const [loading, setLoading] = useState(false)
  const [justSaved, setJustSaved] = useState(false)

  const loadData = useCallback(async () => {
    const kbRes = await knowledgeApi.listKBs()
    setAllKBs(kbRes.items)
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  function toggleKB(kbId: string) {
    setKbIds((prev) =>
      prev.includes(kbId) ? prev.filter((id) => id !== kbId) : [...prev, kbId],
    )
  }

  async function handleSave() {
    setLoading(true)
    try {
      await agentApi.update(agent.id, {
        knowledge_base_ids: kbIds,
        retrieval_config: { top_k: topK, rewrite },
      })
      onUpdated()
      setJustSaved(true)
      setTimeout(() => setJustSaved(false), 1500)
      toast.success("知识库配置已保存")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败")
    } finally {
      setLoading(false)
    }
  }

  const availableKBs = allKBs.filter((kb) => !kbIds.includes(kb.id))

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        {/* KB Association */}
        <Card size="sm">
          <CardHeader className="border-b">
            <CardTitle>关联知识库</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 pt-4">
            {kbIds.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {kbIds.map((id) => {
                  const kb = allKBs.find((k) => k.id === id)
                  return (
                    <Badge key={id} variant="secondary" className="gap-1 pr-1">
                      {kb?.name ?? id}
                      <button
                        type="button"
                        onClick={() => toggleKB(id)}
                        className="rounded-full p-0.5 hover:bg-foreground/10"
                      >
                        <X className="size-3" />
                      </button>
                    </Badge>
                  )
                })}
              </div>
            )}
            <Select value="" onValueChange={(v) => { if (v) toggleKB(v) }}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={availableKBs.length === 0 ? "无更多可选知识库" : "选择知识库..."} />
              </SelectTrigger>
              <SelectContent>
                {availableKBs.map((kb) => (
                  <SelectItem key={kb.id} value={kb.id}>{kb.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              在 Prompt 中使用 <code className="rounded bg-muted px-1">{"{{context}}"}</code> 才会触发检索。
              当前 {kbIds.length} 个关联。
            </p>
          </CardContent>
        </Card>

        {/* Retrieval Config */}
        <Card size="sm">
          <CardHeader className="border-b">
            <CardTitle>检索配置</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 pt-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="top-k">Top K</Label>
              <Input
                id="top-k"
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value) || 5)}
                className="w-24"
              />
              <p className="text-xs text-muted-foreground">每次检索返回最相关的片段数量（1-20）</p>
            </div>
            <div className="flex items-center gap-3">
              <Switch
                id="rewrite"
                checked={rewrite}
                onCheckedChange={(v) => setRewrite(v as boolean)}
              />
              <Label htmlFor="rewrite">查询改写</Label>
            </div>
          </CardContent>
        </Card>

        <div>
          <Button
            onClick={handleSave}
            disabled={loading || justSaved}
            variant={justSaved ? "outline" : "default"}
            className={justSaved ? "text-success border-success/40" : ""}
          >
            {loading
              ? "保存中..."
              : justSaved
              ? <><Check className="mr-1 size-4" /> 已保存</>
              : "保存配置"}
          </Button>
        </div>
      </div>
    </div>
  )
}
