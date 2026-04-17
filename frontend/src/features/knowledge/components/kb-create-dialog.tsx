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
import { knowledgeApi } from "@/api/knowledge"
import { modelApi, type RegistryEntry } from "@/api/model"
import { systemApi } from "@/api/system"

interface KBCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}

const PRESET_LABELS: Record<string, string> = { general: "通用", qa: "问答对", book: "书籍/长文", technical: "技术文档", paper: "论文/报告", custom: "自定义" }

export function KBCreateDialog({ open, onOpenChange, onCreated }: KBCreateDialogProps) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [shareToDept, setShareToDept] = useState(true)
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
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    modelApi.listRegistry({ model_type: "embedding", enabled_only: "true" })
      .then((res) => setEmbModels(Array.isArray(res) ? res : []))
      .catch(() => {})
    systemApi.getSettings()
      .then((s) => setDefaultEmbId((s.default_embedding_model_id as string | undefined) ?? ""))
      .catch(() => setDefaultEmbId(""))
  }, [open])

  function reset() {
    setName("")
    setDescription("")
    setShareToDept(true)
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
        embedding_model_id: embModelId || undefined,
        chunking_config: chunkingPreset === "custom"
          ? { preset: "custom", chunk_size: customChunkSize, chunk_overlap: customOverlap, delimiter: customDelimiter, layout_recognize: layoutRecognize, auto_keywords: autoKeywords, auto_questions: autoQuestions }
          : { preset: chunkingPreset },
        share_to_dept: shareToDept,
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
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="kb-name">名称 *</Label>
            <Input
              id="kb-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="输入知识库名称"
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="kb-desc">描述</Label>
            <Textarea
              id="kb-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="可选描述"
              rows={3}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Embedding 模型</Label>
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
          <div className="flex flex-col gap-2">
            <Label>分片预设</Label>
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
          <div className="flex items-center gap-2">
            <Checkbox
              id="kb-share"
              checked={shareToDept}
              onCheckedChange={(v) => setShareToDept(v as boolean)}
            />
            <Label htmlFor="kb-share">共享至部门</Label>
          </div>
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
