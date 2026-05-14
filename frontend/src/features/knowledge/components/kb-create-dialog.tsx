import { useEffect, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { Switch } from "@/components/ui/switch"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { AlertTriangle } from "lucide-react"
import { knowledgeApi, type KBSourceType } from "@/api/knowledge"
import { modelApi, type RegistryEntry } from "@/api/model"
import { sourcesApi } from "@/api/sources"
import { systemApi } from "@/api/system"
import { cn } from "@/lib/utils"

interface SourceTypeMeta {
  value: KBSourceType
  icon: string
  label: string
  description: string
}

// 仅 UI 层面的 icon/label/description 配置；"是否启用" 由后端 sources endpoint 决定
const SOURCE_TYPE_META: SourceTypeMeta[] = [
  { value: "file", icon: "📁", label: "文件型", description: "上传文档自动切片，适合 PDF / Word / Markdown 等" },
  { value: "entry", icon: "📋", label: "条目型", description: "在线编辑标准条目，适合 FAQ / SOP / 客服话术" },
  { value: "git_repo", icon: "💻", label: "代码型", description: "Git 仓库，按函数/类切片" },
  { value: "confluence", icon: "🔗", label: "外部同步", description: "Confluence / Notion 同步" },
]

interface KBCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}

const PRESET_LABELS: Record<string, string> = { general: "通用", qa: "问答对", book: "书籍/长文", technical: "技术文档", paper: "论文/报告", custom: "自定义" }

export function KBCreateDialog({ open, onOpenChange, onCreated }: KBCreateDialogProps) {
  const [sourceType, setSourceType] = useState<KBSourceType>("file")
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [shareToDept, setShareToDept] = useState(true)
  // Spec 25 §6.2 — 启用智能标签子系统（auto_tag pipeline + L4 boost + L5 routing）
  const [enableAutoTagging, setEnableAutoTagging] = useState(true)
  const [embModelId, setEmbModelId] = useState("")
  const [chunkingPreset, setChunkingPreset] = useState("general")
  const [customChunkSize, setCustomChunkSize] = useState(512)
  const [customOverlap, setCustomOverlap] = useState(50)
  const [customDelimiter, setCustomDelimiter] = useState("\\n")
  const [layoutRecognize, setLayoutRecognize] = useState(true)
  const [autoKeywords, setAutoKeywords] = useState(false)
  const [autoQuestions, setAutoQuestions] = useState(false)
  const [embModels, setEmbModels] = useState<RegistryEntry[]>([])
  const [defaultEmbId, setDefaultEmbId] = useState<string>("")
  const [enabledSourceTypes, setEnabledSourceTypes] = useState<Set<string>>(new Set(["file"]))
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    modelApi.listRegistry({ model_type: "embedding", enabled_only: "true" })
      .then((res) => setEmbModels(Array.isArray(res) ? res : []))
      .catch(() => {})
    systemApi.getSettings()
      .then((s) => setDefaultEmbId((s.default_embedding_model_id as string | undefined) ?? ""))
      .catch(() => setDefaultEmbId(""))
    // P19 — 后端动态拉取已注册 source_types，加新 plugin 自动显示
    sourcesApi.list()
      .then((rows) => setEnabledSourceTypes(new Set(rows.map((r) => r.source_type))))
      .catch(() => setEnabledSourceTypes(new Set(["file"])))
  }, [open])

  function reset() {
    setSourceType("file")
    setName("")
    setDescription("")
    setShareToDept(true)
    setEnableAutoTagging(true)
    setEmbModelId("")
    setChunkingPreset("general")
    setCustomChunkSize(512)
    setCustomOverlap(50)
    setCustomDelimiter("\\n")
    setLayoutRecognize(true)
    setAutoKeywords(false)
    setAutoQuestions(false)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return

    setLoading(true)
    try {
      await knowledgeApi.createKB({
        name: name.trim(),
        description: description.trim() || undefined,
        source_type: sourceType,
        embedding_model_id: embModelId || undefined,
        // 条目型不需要 chunking_config（由 EntrySourcePlugin 内部降级切片处理）
        chunking_config: sourceType !== "file"
          ? undefined
          : chunkingPreset === "custom"
            ? { preset: "custom", chunk_size: customChunkSize, chunk_overlap: customOverlap, delimiter: customDelimiter, layout_recognize: layoutRecognize, auto_keywords: autoKeywords, auto_questions: autoQuestions }
            : { preset: chunkingPreset },
        share_to_dept: shareToDept,
        enable_auto_tagging: enableAutoTagging,
      })
      reset()
      onOpenChange(false)
      onCreated()
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v)
        if (!v) reset()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>创建知识库</DialogTitle>
          <DialogDescription>创建一个新的知识库来管理文档和知识</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          {/* 身份信息 — 主区 */}
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="kb-name" className="text-sm">名称 <span className="text-destructive">*</span></Label>
              <Input
                id="kb-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：运维知识库 / 客服 SOP"
                required
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="kb-desc" className="text-sm">描述</Label>
              <Textarea
                id="kb-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="一句话说明这个知识库的用途"
                rows={2}
              />
            </div>
          </div>

          {/* 类型选择 — 紧跟身份信息 */}
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between">
              <Label className="text-sm">类型</Label>
              <span className="text-[10px] text-muted-foreground">建库后不可修改</span>
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {SOURCE_TYPE_META.map((opt) => {
                const enabled = enabledSourceTypes.has(opt.value)
                const selected = enabled && sourceType === opt.value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    disabled={!enabled}
                    onClick={() => enabled && setSourceType(opt.value)}
                    title={enabled ? opt.description : `${opt.description}（即将开放）`}
                    className={cn(
                      "group flex flex-col items-center gap-1 rounded-md border px-2 py-2.5 transition-all",
                      !enabled && "cursor-not-allowed opacity-40",
                      selected
                        ? "border-primary bg-primary/5 shadow-sm"
                        : enabled && "hover:border-primary/50 hover:bg-muted/40",
                    )}
                  >
                    <span className="text-base leading-none">{opt.icon}</span>
                    <span className="text-xs font-medium leading-none">{opt.label}</span>
                  </button>
                )
              })}
            </div>
            {/* 当前选中类型的描述（避免每个 chip 上挤满字） */}
            <p className="text-[11px] text-muted-foreground">
              {SOURCE_TYPE_META.find((o) => o.value === sourceType)?.description}
            </p>
          </div>

          {/* 高级配置 — 模型 / 切片 / 共享 */}
          <div className="space-y-3 border-t pt-4">
          <div className="flex flex-col gap-1.5">
            <Label className="text-sm">Embedding 模型</Label>
            <Select value={embModelId || undefined} onValueChange={(v) => v != null && setEmbModelId(v)}>
              <SelectTrigger className="w-full">
                {embModelId ? (
                  <span className="truncate">{(() => { const m = embModels.find(e => e.id === embModelId); return m ? `${m.display_name || m.model_id} (${m.provider_name || "未知"})` : embModelId })()}</span>
                ) : defaultEmbId ? (
                  <span className="truncate text-muted-foreground">
                    使用系统默认（{(() => { const m = embModels.find(e => e.id === defaultEmbId); return m ? (m.display_name || m.model_id) : "已设" })()}）
                  </span>
                ) : (
                  <SelectValue placeholder="选择 Embedding 模型" />
                )}
              </SelectTrigger>
              <SelectContent>
                {embModels.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.display_name || m.model_id} ({m.provider_name || "未知"})
                    {m.id === defaultEmbId && <span className="ml-1 text-[10px] text-muted-foreground">· 默认</span>}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!embModelId && !defaultEmbId && (
              <div className="flex items-start gap-1.5 rounded-md border border-warning/40 bg-warning/10 px-2.5 py-1.5 text-xs text-warning-foreground">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  未选择且系统尚未配置默认 Embedding。
                  创建后知识库将无法上传和检索，请先到「设置 → 模型 → 默认模型」配置。
                </span>
              </div>
            )}
          </div>
          {/* 条目型不需要 chunking 配置（降级切片自动处理） */}
          {sourceType === "file" && <div className="flex flex-col gap-1.5">
            <Label className="text-sm">分片预设</Label>
            <Select value={chunkingPreset} onValueChange={(v) => v && setChunkingPreset(v)}>
              <SelectTrigger className="w-full">
                {chunkingPreset
                  ? <span>{PRESET_LABELS[chunkingPreset] ?? chunkingPreset}</span>
                  : <SelectValue />}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="general">通用</SelectItem>
                <SelectItem value="qa">问答对</SelectItem>
                <SelectItem value="book">书籍/长文</SelectItem>
                <SelectItem value="technical">技术文档</SelectItem>
                <SelectItem value="paper">论文/报告</SelectItem>
                <SelectItem value="custom">自定义</SelectItem>
              </SelectContent>
            </Select>
          </div>}
          {sourceType === "file" && chunkingPreset === "custom" && (
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
                <p className="text-[10px] text-muted-foreground">启用后使用 AI 识别文档版面结构（标题/表格/列表），提高分片质量，处理速度略慢</p>
              </div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">自动关键词</Label>
                <Switch checked={autoKeywords} onCheckedChange={(v) => setAutoKeywords(v as boolean)} />
              </div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">自动问题生成</Label>
                <Switch checked={autoQuestions} onCheckedChange={(v) => setAutoQuestions(v as boolean)} />
              </div>
              <p className="text-[10px] text-muted-foreground">自动关键词/问题：为每个分片通过 LLM 生成关键词或问题，增强检索召回率，消耗额外 token</p>
            </div>
          )}
          <div className="flex items-center gap-2 pt-1">
            <Checkbox
              id="kb-share"
              checked={shareToDept}
              onCheckedChange={(v) => setShareToDept(v as boolean)}
            />
            <Label htmlFor="kb-share" className="text-sm font-normal">共享至我的部门</Label>
          </div>
          {/* Spec 25 §6.2 — 智能标签总开关；详细配置在 KB 详情页 config tab */}
          <div className="flex items-start gap-2 pt-1">
            <Switch
              id="kb-auto-tag"
              checked={enableAutoTagging}
              onCheckedChange={(v) => setEnableAutoTagging(v as boolean)}
            />
            <div className="flex-1">
              <Label htmlFor="kb-auto-tag" className="text-sm font-normal">启用智能标签</Label>
              <p className="text-[10px] text-muted-foreground">
                建库后自动从条目内容提取标签，并启用基于标签的检索增强（语义过滤 / 重排 / 智能路由）；
                详细参数可在 KB 配置页调整
              </p>
            </div>
          </div>
          </div>{/* 高级配置 end */}
          <DialogFooter>
            <Button variant="outline" type="button" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" disabled={!name.trim() || loading}>
              {loading ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
