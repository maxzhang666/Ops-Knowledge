import { useEffect, useState } from "react"
import { Check, Trash2, AlertTriangle } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Card, CardHeader, CardTitle, CardDescription, CardContent,
} from "@/components/ui/card"
import { knowledgeApi, type KnowledgeBase } from "@/api/knowledge"
import { modelApi, type RegistryEntry } from "@/api/model"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"

interface ConfigTabProps {
  kb: KnowledgeBase
  onUpdated: () => void
  onDeleted?: () => void
}

const CHUNKING_PRESETS: { value: string; label: string }[] = [
  { value: "general", label: "通用" },
  { value: "qa", label: "问答对" },
  { value: "book", label: "书籍/长文" },
  { value: "technical", label: "技术文档" },
  { value: "paper", label: "论文/报告" },
  { value: "custom", label: "自定义" },
]

// Returns a stateful "just saved" flag that stays true for `durationMs`
// after set(true), then auto-flips to false. Used to keep the Save button
// visible with a "已保存 ✓" label briefly after success, instead of the
// button vanishing the instant state syncs back to `!changed`.
function useJustSaved(durationMs = 1500) {
  const [flag, setFlag] = useState(false)
  function trigger() {
    setFlag(true)
    setTimeout(() => setFlag(false), durationMs)
  }
  return [flag, trigger] as const
}

export function ConfigTab({ kb, onUpdated, onDeleted }: ConfigTabProps) {
  // --- Basic info ---
  const [name, setName] = useState(kb.name)
  const [description, setDescription] = useState(kb.description ?? "")
  const [savingBasic, setSavingBasic] = useState(false)
  const [basicJustSaved, triggerBasicSaved] = useJustSaved()

  // --- Embedding ---
  const [embModels, setEmbModels] = useState<RegistryEntry[]>([])
  const [embModelId, setEmbModelId] = useState(kb.embedding_model_id ?? "")
  const [savingEmb, setSavingEmb] = useState(false)
  const [embJustSaved, triggerEmbSaved] = useJustSaved()

  // --- Chunking ---
  const chunkCfg = kb.chunking_config as Record<string, unknown> | null
  const [chunkingPreset, setChunkingPreset] = useState(
    (chunkCfg?.preset as string) ?? "general",
  )
  const [customChunkSize, setCustomChunkSize] = useState((chunkCfg?.chunk_size as number) ?? 512)
  const [customOverlap, setCustomOverlap] = useState((chunkCfg?.chunk_overlap as number) ?? 50)
  const [customDelimiter, setCustomDelimiter] = useState((chunkCfg?.delimiter as string) ?? "\\n")
  const [layoutRecognize, setLayoutRecognize] = useState((chunkCfg?.layout_recognize as boolean) ?? true)
  const [autoKeywords, setAutoKeywords] = useState((chunkCfg?.auto_keywords as boolean) ?? false)
  const [autoQuestions, setAutoQuestions] = useState((chunkCfg?.auto_questions as boolean) ?? false)
  const [useRaptor, setUseRaptor] = useState((chunkCfg?.use_raptor as boolean) ?? false)
  const [raptorMaxLevels, setRaptorMaxLevels] = useState((chunkCfg?.raptor_max_levels as number) ?? 3)
  const [savingChunk, setSavingChunk] = useState(false)
  const [chunkJustSaved, triggerChunkSaved] = useJustSaved()

  // --- Retrieval ---
  const retrievalCfg = kb.retrieval_config as Record<string, unknown> | null
  const [topK, setTopK] = useState<number>((retrievalCfg?.top_k as number) ?? 5)
  const [rewrite, setRewrite] = useState<boolean>((retrievalCfg?.rewrite as boolean) ?? false)
  const [rerank, setRerank] = useState<boolean>(
    Boolean(retrievalCfg?.reranker_provider_id && retrievalCfg?.reranker_model_name),
  )
  const [savingRetrieval, setSavingRetrieval] = useState(false)
  const [retrievalJustSaved, triggerRetrievalSaved] = useJustSaved()

  type RetrievalPreset = "precise" | "balanced" | "broad"
  // Spec 01 §Layer 4 preset templates
  function applyPreset(preset: RetrievalPreset) {
    if (preset === "precise") {
      setTopK(3); setRerank(true); setRewrite(false)
    } else if (preset === "balanced") {
      setTopK(5); setRerank(true); setRewrite(true)
    } else {
      setTopK(10); setRerank(false); setRewrite(true)
    }
  }

  useEffect(() => {
    modelApi.listRegistry({ model_type: "embedding", enabled_only: "true" })
      .then((res) => setEmbModels(Array.isArray(res) ? res : []))
      .catch(() => {})
  }, [])

  // Sync local state when kb prop changes
  useEffect(() => {
    setName(kb.name)
    setDescription(kb.description ?? "")
    setEmbModelId(kb.embedding_model_id ?? "")
    setChunkingPreset(
      (kb.chunking_config as Record<string, unknown>)?.preset as string ?? "general",
    )
    const cfg = kb.retrieval_config as Record<string, unknown> | null
    setTopK((cfg?.top_k as number) ?? 5)
    setRewrite((cfg?.rewrite as boolean) ?? false)
  }, [kb])

  const basicChanged = name !== kb.name || description !== (kb.description ?? "")
  const embChanged = embModelId !== (kb.embedding_model_id ?? "")
  const origCfg = (kb.chunking_config as Record<string, unknown>) ?? {}
  const chunkChanged = (
    chunkingPreset !== ((origCfg.preset as string) ?? "general")
    || autoKeywords !== ((origCfg.auto_keywords as boolean) ?? false)
    || autoQuestions !== ((origCfg.auto_questions as boolean) ?? false)
    || useRaptor !== ((origCfg.use_raptor as boolean) ?? false)
    || raptorMaxLevels !== ((origCfg.raptor_max_levels as number) ?? 3)
  )
  const retrievalChanged =
    topK !== ((retrievalCfg?.top_k as number) ?? 5) ||
    rewrite !== ((retrievalCfg?.rewrite as boolean) ?? false) ||
    rerank !== Boolean(retrievalCfg?.reranker_provider_id && retrievalCfg?.reranker_model_name)

  // Optimistic concurrency: include the KB's `updated_at` with each write.
  // Server rejects with 409 if it's stale (modified by another session in between).
  const ifUnmodifiedSince = kb.updated_at

  function handleSaveError(err: unknown) {
    if (err instanceof Error && /409/.test(err.message)) {
      toast.error("该知识库已被其他会话修改，请刷新后再保存")
      onUpdated()  // pull latest so user can retry with fresh base
    } else {
      toast.error(err instanceof Error ? err.message : "保存失败")
    }
  }

  async function saveBasic() {
    setSavingBasic(true)
    try {
      await knowledgeApi.updateKB(kb.id, {
        name: name.trim(),
        description: description.trim() || undefined,
      }, ifUnmodifiedSince)
      onUpdated()
      triggerBasicSaved()
      toast.success("基本信息已保存")
    } catch (err) {
      handleSaveError(err)
    } finally {
      setSavingBasic(false)
    }
  }

  const [embConfirmOpen, setEmbConfirmOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleDeleteKB() {
    setDeleting(true)
    try {
      await knowledgeApi.deleteKB(kb.id)
      toast.success(`已删除 "${kb.name}"`)
      setDeleteOpen(false)
      onDeleted?.()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
      setDeleting(false)
    }
  }
  async function doSaveEmbedding() {
    setSavingEmb(true)
    try {
      await knowledgeApi.updateKB(kb.id, { embedding_model_id: embModelId }, ifUnmodifiedSince)
      onUpdated()
      triggerEmbSaved()
      toast.success("Embedding 模型已更新，知识库将重新索引")
    } catch (err) {
      handleSaveError(err)
    } finally {
      setSavingEmb(false)
      setEmbConfirmOpen(false)
    }
  }

  async function saveChunking() {
    setSavingChunk(true)
    try {
      // Enrichment / RAPTOR flags 与 preset 正交，所有预设都可开启
      const enrichment = {
        auto_keywords: autoKeywords,
        auto_questions: autoQuestions,
        use_raptor: useRaptor,
        raptor_max_levels: raptorMaxLevels,
      }
      const chunkPayload = chunkingPreset === "custom"
        ? { preset: "custom", chunk_size: customChunkSize, chunk_overlap: customOverlap, delimiter: customDelimiter, layout_recognize: layoutRecognize, ...enrichment }
        : { preset: chunkingPreset, ...enrichment }
      await knowledgeApi.updateKB(kb.id, { chunking_config: chunkPayload }, ifUnmodifiedSince)
      onUpdated()
      triggerChunkSaved()
      toast.success("分片配置已保存")
    } catch (err) {
      handleSaveError(err)
    } finally {
      setSavingChunk(false)
    }
  }

  async function saveRetrieval() {
    setSavingRetrieval(true)
    try {
      // Preserve any non-managed retrieval keys (e.g. reranker/provider refs set by admin)
      const merged: Record<string, unknown> = { ...(retrievalCfg ?? {}), top_k: topK, rewrite }
      if (!rerank) {
        delete merged.reranker_provider_id
        delete merged.reranker_model_name
      }
      await knowledgeApi.updateKB(kb.id, { retrieval_config: merged }, ifUnmodifiedSince)
      onUpdated()
      triggerRetrievalSaved()
      toast.success("检索配置已保存")
    } catch (err) {
      handleSaveError(err)
    } finally {
      setSavingRetrieval(false)
    }
  }

  return (
    <div className="mt-4 flex max-w-2xl flex-col gap-6">
      {/* Basic info */}
      <Card>
        <CardHeader>
          <CardTitle>基本信息</CardTitle>
          <CardDescription>知识库名称与描述</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="cfg-name">名称</Label>
            <Input id="cfg-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="cfg-desc">描述</Label>
            <Textarea id="cfg-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </div>
          {(basicChanged || basicJustSaved) && (
            <div className="flex justify-end">
              <Button
                disabled={savingBasic || basicJustSaved || !name.trim()}
                onClick={saveBasic}
                variant={basicJustSaved ? "outline" : "default"}
                className={basicJustSaved ? "text-success border-success/40" : ""}
              >
                {savingBasic
                  ? "保存中..."
                  : basicJustSaved
                  ? <><Check className="mr-1 size-4" /> 已保存</>
                  : "保存"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Embedding */}
      <Card>
        <CardHeader>
          <CardTitle>Embedding 配置</CardTitle>
          <CardDescription>
            当前模型：{kb.embedding_model_name || "未配置"}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label>Embedding 模型</Label>
            <Select value={embModelId || undefined} onValueChange={(v) => v != null && setEmbModelId(v)}>
              <SelectTrigger className="w-full">
                {embModelId
                  ? <span className="truncate">{(() => { const m = embModels.find(e => e.id === embModelId); return m ? `${m.display_name || m.model_id} (${m.provider_name || "未知"})` : embModelId })()}</span>
                  : <SelectValue placeholder="使用系统默认" />}
              </SelectTrigger>
              <SelectContent>
                {embModels.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.display_name || m.model_id} ({m.provider_name || "未知"})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {(embChanged || embJustSaved) && (
            <div className="flex justify-end">
              <Button
                disabled={savingEmb || embJustSaved}
                onClick={() => setEmbConfirmOpen(true)}
                variant={embJustSaved ? "outline" : "default"}
                className={embJustSaved ? "text-success border-success/40" : ""}
              >
                {savingEmb
                  ? "保存中..."
                  : embJustSaved
                  ? <><Check className="mr-1 size-4" /> 已保存</>
                  : "保存"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Chunking */}
      <Card>
        <CardHeader>
          <CardTitle>分片配置</CardTitle>
          <CardDescription>选择文档分片策略预设</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label>分片预设</Label>
            <Select value={chunkingPreset} onValueChange={(v) => v && setChunkingPreset(v)}>
              <SelectTrigger className="w-full">
                {chunkingPreset
                  ? <span>{CHUNKING_PRESETS.find(p => p.value === chunkingPreset)?.label ?? chunkingPreset}</span>
                  : <SelectValue />}
              </SelectTrigger>
              <SelectContent>
                {CHUNKING_PRESETS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {chunkingPreset === "custom" && (
            <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-3">
              <p className="text-xs font-medium text-muted-foreground">高级分片参数</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">分片 Token 数</Label>
                  <Input type="number" min={64} max={4096} value={customChunkSize} onChange={(e) => setCustomChunkSize(Number(e.target.value) || 512)} />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">重叠 Token 数</Label>
                  <Input type="number" min={0} max={512} value={customOverlap} onChange={(e) => setCustomOverlap(Number(e.target.value) || 0)} />
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs">分隔符</Label>
                <Input value={customDelimiter} onChange={(e) => setCustomDelimiter(e.target.value)} placeholder="\n" className="font-mono text-xs" />
                <p className="text-[10px] text-muted-foreground">支持 \n（换行）、\n\n（双换行）、自定义字符</p>
              </div>
              <div className="flex flex-col gap-2 pt-1">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">版面识别</Label>
                  <Switch checked={layoutRecognize} onCheckedChange={(v) => setLayoutRecognize(v as boolean)} />
                </div>
                <p className="text-[10px] text-muted-foreground">启用后使用 AI 识别文档版面结构，提高分片质量</p>
              </div>
            </div>
          )}
          {/* LLM 增强（所有 preset 共用）—— P24.M5 */}
          <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">LLM 增强</p>
                <p className="text-[11px] text-muted-foreground">开启后每个切片会额外调用系统默认 LLM，消耗 token</p>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-xs">自动关键词</Label>
                <p className="text-[10px] text-muted-foreground">每个切片生成 3-5 个关键词，辅助检索召回</p>
              </div>
              <Switch checked={autoKeywords} onCheckedChange={(v) => setAutoKeywords(v as boolean)} />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-xs">自动问题</Label>
                <p className="text-[10px] text-muted-foreground">每个切片生成 1-2 个用户视角的问题</p>
              </div>
              <Switch checked={autoQuestions} onCheckedChange={(v) => setAutoQuestions(v as boolean)} />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-xs">RAPTOR 树形摘要</Label>
                <p className="text-[10px] text-muted-foreground">递归聚类+摘要生成层级 chunk，提升抽象查询效果</p>
              </div>
              <Switch checked={useRaptor} onCheckedChange={(v) => setUseRaptor(v as boolean)} />
            </div>
            {useRaptor && (
              <div className="flex items-center justify-between">
                <Label className="text-xs">RAPTOR 最大层级</Label>
                <Input
                  type="number" min={1} max={5}
                  value={raptorMaxLevels}
                  onChange={(e) => setRaptorMaxLevels(Math.max(1, Math.min(5, Number(e.target.value) || 3)))}
                  className="w-20"
                />
              </div>
            )}
          </div>
          {(chunkChanged || chunkJustSaved) && (
            <div className="flex justify-end">
              <Button
                disabled={savingChunk || chunkJustSaved}
                onClick={saveChunking}
                variant={chunkJustSaved ? "outline" : "default"}
                className={chunkJustSaved ? "text-success border-success/40" : ""}
              >
                {savingChunk
                  ? "保存中..."
                  : chunkJustSaved
                  ? <><Check className="mr-1 size-4" /> 已保存</>
                  : "保存"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Retrieval */}
      <Card>
        <CardHeader>
          <CardTitle>检索配置</CardTitle>
          <CardDescription>一键预设或手动微调检索参数</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {/* Preset buttons */}
          <div className="flex flex-col gap-1">
            <Label>推荐预设</Label>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => applyPreset("precise")}>
                精准（top_k=3, rerank）
              </Button>
              <Button variant="outline" size="sm" onClick={() => applyPreset("balanced")}>
                均衡（top_k=5, rerank+改写）
              </Button>
              <Button variant="outline" size="sm" onClick={() => applyPreset("broad")}>
                广泛（top_k=10, 改写）
              </Button>
            </div>
            <p className="text-[10px] text-muted-foreground">
              精准适合事实查询；均衡适合通用问答；广泛适合总结/探索类问题
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="cfg-topk">Top K</Label>
            <Input
              id="cfg-topk"
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch
              id="cfg-rewrite"
              checked={rewrite}
              onCheckedChange={(v) => setRewrite(v as boolean)}
            />
            <Label htmlFor="cfg-rewrite">查询改写</Label>
          </div>
          <div className="flex items-center gap-3">
            <Switch
              id="cfg-rerank"
              checked={rerank}
              onCheckedChange={(v) => setRerank(v as boolean)}
            />
            <Label htmlFor="cfg-rerank">Rerank（需在高级设置配置 Reranker 模型）</Label>
          </div>
          {(retrievalChanged || retrievalJustSaved) && (
            <div className="flex justify-end">
              <Button
                disabled={savingRetrieval || retrievalJustSaved}
                onClick={saveRetrieval}
                variant={retrievalJustSaved ? "outline" : "default"}
                className={retrievalJustSaved ? "text-success border-success/40" : ""}
              >
                {savingRetrieval
                  ? "保存中..."
                  : retrievalJustSaved
                  ? <><Check className="mr-1 size-4" /> 已保存</>
                  : "保存"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={embConfirmOpen}
        onOpenChange={setEmbConfirmOpen}
        title="更换 Embedding 模型"
        description="更换后知识库中所有文档将被重新索引，可能需要一段时间。确认继续？"
        confirmText="确认更换"
        destructive
        onConfirm={doSaveEmbedding}
      />

      {/* Danger Zone — destructive actions always live at the bottom so they
          sit far from routine Save buttons and can't be triggered by mistake. */}
      <Card className="border-destructive/30">
        <CardHeader className="border-b border-destructive/20 bg-destructive/5">
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="size-4" />
            危险区
          </CardTitle>
          <CardDescription>
            此区域的操作不可撤销，请谨慎操作。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-4 pt-4">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">删除知识库</p>
            <p className="text-xs text-muted-foreground">
              永久删除该知识库及其所有文档、切片、向量和关联数据。无法恢复。
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 className="mr-1.5 size-3.5" /> 删除知识库
          </Button>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={(v) => { if (!deleting) setDeleteOpen(v) }}
        title={`删除知识库 "${kb.name}"`}
        description="此操作将永久删除该知识库及其所有文档、切片、向量数据，无法恢复。请输入知识库名称以确认。"
        confirmText={deleting ? "删除中..." : "永久删除"}
        typeToConfirm={kb.name}
        destructive
        onConfirm={handleDeleteKB}
      />
    </div>
  )
}
