import { useEffect, useState } from "react"
import { Check, Trash2, AlertTriangle } from "lucide-react"
import { toast } from "sonner"
import { Collapse, Select } from "@douyinfe/semi-ui"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { InfoTip } from "@/components/shared/info-tip"
import {
  Card, CardHeader, CardTitle, CardDescription, CardContent,
} from "@/components/ui/card"
import { knowledgeApi, type KnowledgeBase } from "@/api/knowledge"
import { modelApi, type RegistryEntry } from "@/api/model"
import {
  kbTagSettingsApi,
  type KBTagSettings,
  type TagPreset,
  type UpdateKBTagSettings,
} from "@/api/kb_tag_settings"
import { useAuthStore } from "@/stores/auth"
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
  // M6.7 — heading-only 合并 + 短 chunk contextual prefix 阈值
  const [headingOnlyMinChars, setHeadingOnlyMinChars] = useState(
    (chunkCfg?.heading_only_min_chars as number) ?? 30,
  )
  const [contextPrefixMaxChars, setContextPrefixMaxChars] = useState(
    (chunkCfg?.context_prefix_max_chars as number) ?? 100,
  )
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
    || headingOnlyMinChars !== ((origCfg.heading_only_min_chars as number) ?? 30)
    || contextPrefixMaxChars !== ((origCfg.context_prefix_max_chars as number) ?? 100)
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
        // M6.7 — heading-only 合并 + 短 chunk contextual prefix 阈值
        heading_only_min_chars: headingOnlyMinChars,
        context_prefix_max_chars: contextPrefixMaxChars,
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
    // grid auto-fit：单卡最小 360px，浏览器按容器宽度自动决定列数（1 / 2 / 3+）。
    // 高内容卡片（分片 / 智能标签 / 危险区）用 [grid-column:1/-1] 占满整行，避免与
    // 矮卡同行造成视觉跳跃。DESIGN.md §Layout：utility 卡片自然排布、章节用全宽分隔。
    <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(360px,1fr))] gap-6">
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
            <Select
              value={embModelId || undefined}
              onChange={(v) => typeof v === "string" && setEmbModelId(v)}
              placeholder="使用系统默认"
              className="w-full"
              optionList={embModels.map((m) => ({
                value: m.id,
                label: `${m.display_name || m.model_id} (${m.provider_name || "未知"})`,
              }))}
            />
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

      {/* Chunking — 仅文件型 KB 显示（条目型不切片，由降级阈值自动处理）；
          内容多，占满整行避免与矮卡同行视觉跳跃 */}
      {kb.source_type === "file" && <Card className="[grid-column:1/-1]">
        <CardHeader>
          <CardTitle>分片配置</CardTitle>
          <CardDescription>选择文档分片策略预设</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label>分片预设</Label>
            <Select
              value={chunkingPreset}
              onChange={(v) => typeof v === "string" && setChunkingPreset(v)}
              className="w-full"
              optionList={CHUNKING_PRESETS.map((p) => ({ value: p.value, label: p.label }))}
            />
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

            {/* M6.7 — 噪声抑制（多语言 embedding 模型 floor 虚高的两个治理开关） */}
            <div className="border-t pt-3">
              <p className="mb-2 inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                噪声抑制（多语言模型）
                <InfoTip text="工程上叫「Floor 抑制」（M6.6+M6.7）。多语言 embedding 模型（BGE-M3、E5-multilingual、OpenAI text-embedding-3 等）有个通病：跨语言文本对之间余弦相似度有 0.65~0.75 的「下限基线」（floor），把无关的中文查询和英文文档都判成「有点像」。下面两个开关从切片阶段和向量化阶段降低这种噪声。仅多语言模型 + 中英混合知识库需要；纯英文模型/纯中文场景可关闭" />
              </p>
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <Label className="inline-flex items-center gap-1 text-xs">
                      合并孤立标题切片
                      <InfoTip text="工程上叫 heading-only chunk merge（M6.6 A 方案）。「切片（chunk）」= 文档被拆成的小段。「孤立标题切片」= 只有 markdown 标题没什么正文的切片（如「## 概述」单 4 字符）—— 这种切片 embed 时 token 太少，向量被通用语义/special token 主导，跟任何查询都给 floor 高分。本开关：识别这种切片自动合并到下一段有正文的切片里，作为 heading prefix" />
                    </Label>
                    <p className="text-[10px] text-muted-foreground">
                      正文少于此字符数视为「孤立标题」，合并进下一段。设 0 = 关闭
                    </p>
                  </div>
                  <Input
                    type="number" min={0} max={500}
                    value={headingOnlyMinChars}
                    onChange={(e) => setHeadingOnlyMinChars(Math.max(0, Math.min(500, Number(e.target.value) || 0)))}
                    className="w-20 shrink-0"
                  />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <Label className="inline-flex items-center gap-1 text-xs">
                      短切片补充上下文
                      <InfoTip text="工程上叫 contextual embedding（M6.6 B 方案，简化自 Anthropic 提出的 Contextual Retrieval）。短切片 embed 时信息量不足，AI 不知道这段在讲哪个话题。本开关：向量化前自动在切片前面拼上它的章节标题作为上下文（比如「## Frontend\n\n短正文」），让 AI 更懂这段是哪个领域的内容。**仅作用于送给 embedding 模型的字符串，不修改 Milvus 里存的 content，UI 看到的内容不变**" />
                    </Label>
                    <p className="text-[10px] text-muted-foreground">
                      正文少于此字符数时，向量化前自动补章节标题作上下文。设 0 = 关闭
                    </p>
                  </div>
                  <Input
                    type="number" min={0} max={1000}
                    value={contextPrefixMaxChars}
                    onChange={(e) => setContextPrefixMaxChars(Math.max(0, Math.min(1000, Number(e.target.value) || 0)))}
                    className="w-20 shrink-0"
                  />
                </div>
              </div>
              <p className="mt-2 text-[10px] text-muted-foreground">
                改完后需「重新处理」文档才生效（要重新切片 + 重新向量化）
              </p>
            </div>
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
      </Card>}

      {/* Review workflow (Plan 29) */}
      <ReviewToggleCard kb={kb} onUpdated={onUpdated} ifUnmodifiedSince={ifUnmodifiedSince} />

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

      {/* Spec 25 §6 — 智能标签设置（admin only），含 3 档 preset + 高级展开；
          内容多，占满整行 */}
      <TagSettingsCard kbId={kb.id} />

      {/* Danger Zone — 永远放在最底部 + 全宽占据，远离日常 Save 按钮且足够醒目。
          DESIGN.md "chrome 退后"：去掉 header 浅红背景（曾导致与 content 色块断层），
          危险性靠 destructive border + AlertTriangle 图标 + destructive 文案/按钮承担。 */}
      <Card className="border-destructive/30 [grid-column:1/-1]">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="size-4" />
            危险区
          </CardTitle>
          <CardDescription>
            此区域的操作不可撤销，请谨慎操作。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-4">
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


// ─────────────────────────────────────────────────────────────────
// Plan 29 — KB review_required toggle

function ReviewToggleCard({
  kb, onUpdated, ifUnmodifiedSince,
}: {
  kb: KnowledgeBase
  onUpdated: () => void
  ifUnmodifiedSince: string
}) {
  const [enabled, setEnabled] = useState<boolean>(kb.review_required ?? false)
  const [saving, setSaving] = useState(false)
  const dirty = enabled !== (kb.review_required ?? false)

  async function save() {
    setSaving(true)
    try {
      await knowledgeApi.updateKB(kb.id, { review_required: enabled }, ifUnmodifiedSince)
      toast.success(enabled ? "已开启知识审批" : "已关闭知识审批")
      onUpdated()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败")
      setEnabled(kb.review_required ?? false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>知识审批</CardTitle>
        <CardDescription>
          开启后，新上传文档处理完成会进入审批队列，仅审批通过后才参与检索
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-3">
        <div>
          <Label className="text-sm">审批工作流</Label>
          <p className="text-[11px] text-muted-foreground">
            通知 KB 责任人 + 同部门管理员；上传者不能审批自己的文档
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Switch checked={enabled} onCheckedChange={(v) => setEnabled(Boolean(v))} />
          {dirty && (
            <Button size="sm" onClick={save} disabled={saving}>
              {saving ? "保存中..." : "保存"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}


// ─────────────────────────────────────────────────────────────────
// Spec 25 §6 — 智能标签设置卡（admin only）
// 3 档 preset radio + 高级 collapsible 展开各字段；
// 任一字段改动自动转 custom；UI 仅 system_admin 渲染。

const TAG_PRESETS: { value: Exclude<TagPreset, "custom">; label: string; desc: string }[] = [
  { value: "low_cost", label: "低成本", desc: "KeyBERT，max 3 标签，置信度阈值 0.7" },
  { value: "balanced", label: "均衡（推荐）", desc: "Hybrid，max 5 标签，置信度 0.6" },
  { value: "high_quality", label: "高质量", desc: "LLM，max 8 标签，置信度 0.5，启用智能路由" },
]

// Spec 25 — provider 下拉选项；本组件已用 Semi Select（天然显示 label 而非 value）；
// hint 走 Select renderOptionItem 自定义两段式选项展示
const TAG_PROVIDER_OPTIONS: { value: KBTagSettings["auto_tag_provider"]; label: string; hint: string }[] = [
  { value: "keybert", label: "KeyBERT", hint: "仅 embedding，无 LLM 成本" },
  { value: "llm", label: "LLM", hint: "小模型抽取" },
  { value: "hybrid", label: "Hybrid", hint: "KeyBERT 候选 + LLM 改写" },
]

function TagSettingsCard({ kbId }: { kbId: string }) {
  const role = useAuthStore((s) => s.user?.role)
  const [data, setData] = useState<KBTagSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [llmOptions, setLlmOptions] = useState<RegistryEntry[]>([])

  useEffect(() => {
    let cancelled = false
    kbTagSettingsApi.get(kbId)
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [kbId])

  useEffect(() => {
    modelApi.listRegistry({ model_type: "llm", enabled_only: "true" })
      .then((l) => setLlmOptions(Array.isArray(l) ? l : []))
      .catch(() => {})
  }, [])

  // 仅 system_admin 可见，避免普通用户被复杂参数干扰
  if (role !== "system_admin") return null

  async function patch(update: UpdateKBTagSettings) {
    setSaving(true)
    try {
      const next = await kbTagSettingsApi.update(kbId, update)
      setData(next)
      toast.success("已保存")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <Card className="[grid-column:1/-1]">
        <CardHeader><CardTitle>智能标签设置</CardTitle></CardHeader>
        <CardContent><p className="text-xs text-muted-foreground">加载中…</p></CardContent>
      </Card>
    )
  }
  if (!data) {
    return (
      <Card className="[grid-column:1/-1]">
        <CardHeader><CardTitle>智能标签设置</CardTitle></CardHeader>
        <CardContent><p className="text-xs text-muted-foreground">无法加载配置，请刷新页面重试</p></CardContent>
      </Card>
    )
  }

  return (
    <Card className="[grid-column:1/-1]">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>智能标签设置</span>
          <span className="text-[11px] font-normal text-muted-foreground">
            preset: {data.preset}
          </span>
        </CardTitle>
        <CardDescription>
          自动标签提取 + 检索增强（语义过滤 / 重排 / 智能路由）；
          仅管理员可调整。详细统计在「治理」tab 内查看。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* 启用总开关 */}
        <div className="flex items-start gap-3 rounded-md border bg-muted/20 p-3">
          <Switch
            checked={data.auto_tag_enabled}
            onCheckedChange={(v) => patch({ auto_tag_enabled: v as boolean })}
            disabled={saving}
          />
          <div className="flex-1">
            <Label className="text-sm font-medium">启用自动标签提取</Label>
            <p className="text-xs text-muted-foreground">
              关闭后所有条目不再自动生成标签，已有 auto_tags 保留；L4 / L5 也将跳过
            </p>
          </div>
        </div>

        {/* preset 切换 */}
        <div className="flex flex-col gap-2">
          <Label>预设档</Label>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {TAG_PRESETS.map((p) => {
              const active = data.preset === p.value
              return (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => !saving && patch({ preset: p.value })}
                  disabled={saving}
                  className={
                    "rounded-md border p-2.5 text-left transition-colors " +
                    (active
                      ? "border-primary bg-primary/5"
                      : "hover:border-primary/30")
                  }
                >
                  <div className="flex items-center justify-between text-sm font-medium">
                    {p.label}
                    {active && <Check className="size-3.5 text-primary" />}
                  </div>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">{p.desc}</p>
                </button>
              )
            })}
          </div>
          {data.preset === "custom" && (
            <p className="text-[11px] text-warning">
              当前为 custom 模式（用户已偏离预设）；切回预设会覆盖所有自定义值
            </p>
          )}
        </div>

        {/* 高级展开：Semi Collapse 替代手写按钮 + 条件渲染，得到一致的展开动画/可访问性 */}
        <Collapse
          activeKey={showAdvanced ? ["adv"] : []}
          onChange={(keys) => setShowAdvanced(Array.isArray(keys) && keys.includes("adv"))}
        >
          <Collapse.Panel header="高级参数" itemKey="adv">
          <div className="grid grid-cols-1 gap-3 rounded-md border bg-muted/20 p-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label className="text-xs">Provider</Label>
              {/* Semi Select 天然显示 label 而非 value，无需 label-aware hack；
                  renderOptionItem 自定义"label + 灰 hint"两段式选项 */}
              <Select
                value={data.auto_tag_provider}
                onChange={(v) => typeof v === "string" && patch({ auto_tag_provider: v as KBTagSettings["auto_tag_provider"] })}
                className="w-full"
                optionList={TAG_PROVIDER_OPTIONS.map((p) => ({
                  value: p.value,
                  label: p.label,
                  // Semi 允许 extra fields 透传到 renderOptionItem
                  hint: p.hint,
                }))}
                renderOptionItem={(renderProps) => (
                  <div
                    role="option"
                    aria-selected={renderProps.selected}
                    onClick={renderProps.onClick}
                    onMouseEnter={renderProps.onMouseEnter}
                    className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-accent ${renderProps.selected ? "bg-accent/60" : ""}`}
                  >
                    <span className="font-medium">{renderProps.label}</span>
                    <span className="text-xs text-muted-foreground">
                      {(renderProps as unknown as { hint?: string }).hint}
                    </span>
                  </div>
                )}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs">LLM 模型（auto_tag + routing 共用）</Label>
              <Select
                value={data.auto_tag_llm_model_id ?? "__none__"}
                onChange={(v) => patch({
                  auto_tag_llm_model_id: v === "__none__" ? null : (v as string),
                })}
                className="w-full"
                optionList={[
                  { value: "__none__", label: "（未配置 / 跳过）" },
                  ...llmOptions.map((m) => ({
                    value: m.id,
                    label: m.display_name || m.model_id,
                  })),
                ]}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs">每条目最多标签数 ({data.auto_tag_max_per_unit})</Label>
              <Input
                type="number" min={1} max={20}
                value={data.auto_tag_max_per_unit}
                onChange={(e) => patch({ auto_tag_max_per_unit: Number(e.target.value) || 5 })}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs">置信度阈值 ({data.auto_tag_confidence_threshold.toFixed(2)})</Label>
              <Input
                type="number" min={0} max={1} step={0.05}
                value={data.auto_tag_confidence_threshold}
                onChange={(e) => patch({ auto_tag_confidence_threshold: Number(e.target.value) || 0.6 })}
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={data.tag_filter_enabled}
                onCheckedChange={(v) => patch({ tag_filter_enabled: v as boolean })}
              />
              <Label className="text-xs">启用 L1/L2 标签注入与过滤
                <InfoTip text="L1: embedding 前缀注入；L2: 检索 milvus array filter。关闭后召回完全不用 tag 信号" />
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={data.tag_routing_enabled}
                onCheckedChange={(v) => patch({ tag_routing_enabled: v as boolean })}
              />
              <Label className="text-xs">启用 L5 LLM 智能路由
                <InfoTip text="检索前 LLM 推断 query 相关 canonical 自动 any_of。需要配置 LLM 模型" />
              </Label>
            </div>
            <div className="col-span-1 flex flex-col gap-1 sm:col-span-2">
              <Label className="text-xs">L4 重排 boost 权重 ({data.tag_boost_weight.toFixed(3)})</Label>
              <Input
                type="number" min={0} max={1} step={0.01}
                value={data.tag_boost_weight}
                onChange={(e) => patch({ tag_boost_weight: Number(e.target.value) || 0 })}
              />
              <p className="text-[10px] text-muted-foreground">
                每命中一个相关 canonical 给 fused score 增加此权重；0 = 关闭 boost
              </p>
            </div>
          </div>
          </Collapse.Panel>
        </Collapse>
      </CardContent>
    </Card>
  )
}

