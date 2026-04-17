import { useCallback, useEffect, useRef, useState } from "react"
import { Eye, Check, Trash2, AlertTriangle } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"

import {
  agentApi,
  type Agent,
  type PromptPreviewResponse,
  type PromptTemplate,
  type ThinkingDetail,
} from "@/api/agent"
import { modelApi, type RegistryEntry } from "@/api/model"

const THINKING_LABELS: Record<string, string> = {
  minimal: "精简",
  normal: "标准",
  verbose: "详细",
}

const PROMPT_VARS = [
  { name: "{{context}}", hint: "检索到的知识库资料（含 {{context}} 时自动启用 RAG）" },
  { name: "{{history_summary}}", hint: "历史对话摘要" },
  { name: "{{query}}", hint: "当前用户问题" },
  { name: "{{knowledge_names}}", hint: "关联知识库名称列表" },
  { name: "{{kb_count}}", hint: "关联知识库数量" },
]

interface PersonaPanelProps {
  agent: Agent
  onUpdated: () => void
  onDeleted?: () => void  // parent (detail page) navigates back to list
}

export function PersonaPanel({ agent, onUpdated, onDeleted }: PersonaPanelProps) {
  // Model
  const [llmModels, setLlmModels] = useState<RegistryEntry[]>([])
  const [modelId, setModelId] = useState(agent.model_id || "")

  // Prompt
  const [systemPrompt, setSystemPrompt] = useState(agent.system_prompt ?? "")
  const [welcomeMessage, setWelcomeMessage] = useState(agent.welcome_message ?? "")
  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<string>("")
  const [pendingTemplateId, setPendingTemplateId] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewData, setPreviewData] = useState<PromptPreviewResponse | null>(null)
  const [previewQuery, setPreviewQuery] = useState("你好")
  const promptRef = useRef<HTMLTextAreaElement | null>(null)

  // Thinking
  const [showThinking, setShowThinking] = useState(agent.show_thinking ?? false)
  const [thinkingDetail, setThinkingDetail] = useState<ThinkingDetail>(
    (agent.thinking_detail ?? "normal") as ThinkingDetail,
  )

  // Share
  const [shareToDept, setShareToDept] = useState(agent.share_to_dept ?? false)

  const [loading, setLoading] = useState(false)
  const [justSaved, setJustSaved] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleDeleteAgent() {
    setDeleting(true)
    try {
      await agentApi.delete(agent.id)
      toast.success(`已删除 "${agent.name}"`)
      setDeleteOpen(false)
      onDeleted?.()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
      setDeleting(false)
    }
  }
  const hasContextVar = systemPrompt.includes("{{context}}")

  const loadData = useCallback(async () => {
    const [modelsRes, tplRes] = await Promise.all([
      modelApi.listRegistry({ model_type: "llm", enabled_only: "true" }),
      agentApi.listPromptTemplates().catch(() => [] as PromptTemplate[]),
    ])
    setLlmModels(Array.isArray(modelsRes) ? modelsRes : [])
    setTemplates(Array.isArray(tplRes) ? tplRes : [])
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  async function handleSave() {
    setLoading(true)
    try {
      await agentApi.update(agent.id, {
        model_id: modelId || undefined,
        system_prompt: systemPrompt,
        welcome_message: welcomeMessage,
        show_thinking: showThinking,
        thinking_detail: thinkingDetail,
        share_to_dept: shareToDept,
      })
      onUpdated()
      setJustSaved(true)
      setTimeout(() => setJustSaved(false), 1500)
      toast.success("配置已保存")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败")
    } finally {
      setLoading(false)
    }
  }

  function applyTemplate(templateId: string) {
    const tpl = templates.find((t) => t.id === templateId)
    if (!tpl) return
    if (systemPrompt.trim()) {
      setPendingTemplateId(templateId)
      return
    }
    setSystemPrompt(tpl.system_prompt)
    setSelectedTemplate(templateId)
  }

  function confirmApplyTemplate() {
    if (!pendingTemplateId) return
    const tpl = templates.find((t) => t.id === pendingTemplateId)
    if (tpl) {
      setSystemPrompt(tpl.system_prompt)
      setSelectedTemplate(pendingTemplateId)
    }
    setPendingTemplateId(null)
  }

  function insertVariable(variable: string) {
    const ta = promptRef.current
    if (!ta) {
      setSystemPrompt((prev) => prev + variable)
      return
    }
    const start = ta.selectionStart ?? systemPrompt.length
    const end = ta.selectionEnd ?? systemPrompt.length
    const next = systemPrompt.slice(0, start) + variable + systemPrompt.slice(end)
    setSystemPrompt(next)
    setTimeout(() => {
      ta.focus()
      ta.setSelectionRange(start + variable.length, start + variable.length)
    }, 0)
  }

  async function handlePreview() {
    setPreviewOpen(true)
    setPreviewLoading(true)
    setPreviewData(null)
    try {
      const data = await agentApi.previewPrompt(agent.id, {
        query: previewQuery || "你好",
        system_prompt: systemPrompt,
      })
      setPreviewData(data)
    } catch (err) {
      setPreviewData({
        messages: [{ role: "error", content: err instanceof Error ? err.message : "预览失败" }],
        detected_variables: [],
        retrieval_will_trigger: false,
      })
    } finally {
      setPreviewLoading(false)
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        {/* Model */}
        <Card size="sm">
          <CardHeader className="border-b">
            <CardTitle>模型</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="flex flex-col gap-2">
              <Label>LLM 模型</Label>
              <Select value={modelId || undefined} onValueChange={(v) => v != null && setModelId(v)}>
                <SelectTrigger className="w-full">
                  {modelId ? (
                    <span className="truncate">
                      {(() => {
                        const m = llmModels.find((e) => e.id === modelId)
                        return m ? `${m.display_name || m.model_id} (${m.provider_name || "未知"})` : modelId
                      })()}
                    </span>
                  ) : (
                    <SelectValue placeholder="选择 LLM 模型" />
                  )}
                </SelectTrigger>
                <SelectContent>
                  {llmModels.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.display_name || m.model_id} ({m.provider_name || "未知"})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Prompt Editor */}
        <Card size="sm">
          <CardHeader className="border-b">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>Prompt 编辑器</CardTitle>
              <div className="flex items-center gap-2">
                <Select
                  value={selectedTemplate || undefined}
                  onValueChange={(v) => v && applyTemplate(v)}
                >
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="加载模板..." />
                  </SelectTrigger>
                  <SelectContent>
                    {templates.map((t) => (
                      <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button type="button" variant="outline" size="sm" onClick={handlePreview}>
                  <Eye className="mr-1 size-3.5" /> 预览
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 pt-4">
            <div className="flex flex-wrap gap-1.5">
              <span className="text-xs text-muted-foreground">可用变量：</span>
              {PROMPT_VARS.map((v) => (
                <Badge
                  key={v.name}
                  variant="outline"
                  title={v.hint}
                  className="cursor-pointer hover:bg-accent"
                  onClick={() => insertVariable(v.name)}
                >
                  {v.name}
                </Badge>
              ))}
            </div>
            <Textarea
              ref={promptRef}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="定义智能体的身份、规则和回答风格。含 {{context}} 时会自动检索知识库。"
              rows={12}
              className="font-mono text-sm"
            />
            <div
              className={
                hasContextVar
                  ? "flex items-start gap-2 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-xs"
                  : "flex items-start gap-2 rounded-md border border-muted bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
              }
            >
              {hasContextVar ? (
                <>
                  <Check className="mt-0.5 size-3.5 shrink-0 text-success" />
                  <span>
                    <span className="font-medium text-success">RAG 模式已启用</span>
                    ：检测到 <code className="rounded bg-background/60 px-1">{"{{context}}"}</code>，
                    此智能体将自动检索关联知识库并注入到 Prompt 中。
                  </span>
                </>
              ) : (
                <>
                  <span className="mt-0.5 inline-block size-3.5 shrink-0 rounded-full border border-muted-foreground/50" />
                  <span>
                    <span className="font-medium text-foreground/80">纯聊天模式</span>
                    ：当前 Prompt 未使用 <code className="rounded bg-background/60 px-1">{"{{context}}"}</code>，不会触发知识库检索。
                    插入该变量即可启用 RAG。
                  </span>
                </>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Welcome Message */}
        <div className="flex flex-col gap-2">
          <Label htmlFor="welcome-msg">欢迎语</Label>
          <Input
            id="welcome-msg"
            value={welcomeMessage}
            onChange={(e) => setWelcomeMessage(e.target.value)}
            placeholder="用户打开对话时的欢迎消息"
          />
        </div>

        {/* Thinking */}
        <Card size="sm">
          <CardHeader className="border-b">
            <CardTitle>思维链</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 pt-4">
            <div className="flex items-center gap-3">
              <Switch
                id="show-thinking"
                checked={showThinking}
                onCheckedChange={(v) => setShowThinking(v as boolean)}
              />
              <Label htmlFor="show-thinking">展示思维过程</Label>
            </div>
            <div className="flex flex-col gap-2">
              <Label>详细度</Label>
              <Select
                value={thinkingDetail}
                onValueChange={(v) => v && setThinkingDetail(v as ThinkingDetail)}
              >
                <SelectTrigger className="w-40">
                  {thinkingDetail ? (
                    <span>{THINKING_LABELS[thinkingDetail] ?? thinkingDetail}</span>
                  ) : (
                    <SelectValue />
                  )}
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="minimal">精简</SelectItem>
                  <SelectItem value="normal">标准</SelectItem>
                  <SelectItem value="verbose">详细</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Share */}
        <div className="flex items-center gap-3">
          <Switch
            id="share-to-dept"
            checked={shareToDept}
            onCheckedChange={(v) => setShareToDept(v as boolean)}
          />
          <Label htmlFor="share-to-dept">共享给部门</Label>
        </div>

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

        {/* Danger Zone — destructive actions far from the save button */}
        {onDeleted && (
          <Card className="mt-4 border-destructive/30">
            <CardHeader className="border-b border-destructive/20 bg-destructive/5">
              <CardTitle className="flex items-center gap-2 text-destructive">
                <AlertTriangle className="size-4" />
                危险区
              </CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between gap-4 pt-4">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">删除智能体</p>
                <p className="text-xs text-muted-foreground">
                  永久删除该智能体及其所有会话历史，无法恢复。
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 className="mr-1.5 size-3.5" /> 删除智能体
              </Button>
            </CardContent>
          </Card>
        )}
      </div>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={(v) => { if (!deleting) setDeleteOpen(v) }}
        title={`删除智能体 "${agent.name}"`}
        description="此操作将永久删除该智能体及其所有会话历史，无法恢复。请输入名称以确认。"
        confirmText={deleting ? "删除中..." : "永久删除"}
        typeToConfirm={agent.name}
        destructive
        onConfirm={handleDeleteAgent}
      />

      {/* Prompt Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Prompt 预览</DialogTitle>
            <DialogDescription>
              模拟发送给 LLM 的完整 messages 列表。变量已替换为示例或实际值。
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Label htmlFor="preview-query" className="whitespace-nowrap">示例问题:</Label>
              <Input
                id="preview-query"
                value={previewQuery}
                onChange={(e) => setPreviewQuery(e.target.value)}
                className="flex-1"
              />
              <Button size="sm" onClick={handlePreview} disabled={previewLoading}>
                {previewLoading ? "生成中..." : "重新生成"}
              </Button>
            </div>
            {previewData && (
              <>
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge variant={previewData.retrieval_will_trigger ? "default" : "secondary"}>
                    {previewData.retrieval_will_trigger ? "将触发检索" : "不触发检索"}
                  </Badge>
                  {previewData.detected_variables.map((v) => (
                    <Badge key={v} variant="outline">{`{{${v}}}`}</Badge>
                  ))}
                </div>
                <div className="max-h-96 overflow-auto rounded border bg-muted/30 p-3">
                  {previewData.messages.map((m, i) => (
                    <div key={i} className="mb-3 last:mb-0">
                      <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">{m.role}</div>
                      <pre className="whitespace-pre-wrap font-mono text-xs">{m.content}</pre>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={pendingTemplateId !== null}
        onOpenChange={(v) => { if (!v) setPendingTemplateId(null) }}
        title="替换当前 Prompt"
        description={
          pendingTemplateId
            ? `将使用模板「${templates.find((t) => t.id === pendingTemplateId)?.name ?? ""}」替换当前 Prompt 内容，确认继续？`
            : ""
        }
        confirmText="替换"
        onConfirm={confirmApplyTemplate}
      />
    </div>
  )
}
