import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
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
import { Badge } from "@/components/ui/badge"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { agentApi, type AgentType } from "@/api/agent"
import { workflowApi, type WorkflowSummary } from "@/api/workflow"
import { cn } from "@/lib/utils"

// Phase 2 delivered by Plan 31 — unlock orchestrator option.
const agentTypeOptions: { value: AgentType; label: string; disabled: boolean; badge?: string }[] = [
  { value: "simple", label: "简易智能体", disabled: false },
  { value: "workflow", label: "工作流智能体", disabled: false },
  { value: "orchestrator", label: "编排智能体", disabled: false, badge: "New" },
]

interface AgentCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}


export function AgentCreateDialog({ open, onOpenChange, onCreated }: AgentCreateDialogProps) {
  const navigate = useNavigate()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [agentType, setAgentType] = useState<AgentType>("simple")
  const [loading, setLoading] = useState(false)
  const [defaultWorkflowId, setDefaultWorkflowId] = useState("")
  const [candidates, setCandidates] = useState<WorkflowSummary[]>([])

  function reset() {
    setName("")
    setDescription("")
    setAgentType("simple")
    setDefaultWorkflowId("")
  }

  // Orchestrator routes to multiple Workflows (each = one SOP canvas).
  // Load Workflows as default_handler candidates.
  useEffect(() => {
    if (!open || agentType !== "orchestrator") return
    workflowApi.list()
      .then((r) => {
        const items = Array.isArray(r) ? r : ((r as { items?: WorkflowSummary[] }).items ?? [])
        setCandidates(items)
      })
      .catch(() => setCandidates([]))
  }, [open, agentType])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return

    if (agentType === "orchestrator" && !defaultWorkflowId) {
      toast.error("编排智能体需要指定默认派发的 Workflow（兜底 SOP）")
      return
    }

    setLoading(true)
    try {
      const payload: Parameters<typeof agentApi.create>[0] = {
        name: name.trim(),
        description: description.trim() || undefined,
        agent_type: agentType,
      }
      if (agentType === "orchestrator") {
        // Minimal valid orchestrator_config: default_handler pointing at
        // the selected Workflow. Classifier + rules added in the workbench.
        payload.orchestrator_config = {
          default_handler: {
            handler_type: "workflow",
            handler_id: defaultWorkflowId,
            handler_config: { input_mapping: { query: "$message" } },
          },
          trusted_metadata_paths: ["user.role", "user.department_id", "user.id"],
          diagnostic_mode_allowed_roles: ["system_admin", "dept_admin"],
          classifier: null,
        }
      }
      const agent = await agentApi.create(payload)
      reset()
      onOpenChange(false)
      onCreated()
      navigate(`/agents/${agent.id}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建失败")
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
          <DialogTitle>创建智能体</DialogTitle>
          <DialogDescription>创建一个新的智能体来处理对话</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="agent-name">名称 *</Label>
            <Input
              id="agent-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="输入智能体名称"
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="agent-desc">描述</Label>
            <Textarea
              id="agent-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="可选描述"
              rows={3}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>智能体类型</Label>
            <div className="flex flex-col gap-1.5">
              {agentTypeOptions.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  disabled={opt.disabled}
                  onClick={() => setAgentType(opt.value)}
                  className={cn(
                    "flex items-center gap-2 rounded-md border px-3 py-2 text-sm text-left transition-colors",
                    agentType === opt.value
                      ? "border-primary bg-primary/5"
                      : "border-input hover:bg-accent",
                    opt.disabled && "cursor-not-allowed opacity-50",
                  )}
                >
                  <span className="flex-1">{opt.label}</span>
                  {opt.badge && (
                    <Badge variant="secondary" className="text-[10px]">
                      {opt.badge}
                    </Badge>
                  )}
                </button>
              ))}
            </div>
          </div>

          {agentType === "workflow" && (
            <p className="rounded-md border border-dashed bg-muted/30 p-2 text-xs text-muted-foreground">
              将自动为该智能体创建一个空白工作流草稿，创建后可在智能体页面内直接编辑。
            </p>
          )}

          {agentType === "orchestrator" && (
            <div className="flex flex-col gap-2">
              <Label>默认派发的 Workflow（兜底）*</Label>
              {candidates.length === 0 ? (
                <p className="rounded-md border border-destructive/50 bg-destructive/5 p-2 text-xs text-destructive">
                  没有可选的 Workflow。请先创建一个 Workflow 作为兜底 SOP。
                </p>
              ) : (
                <>
                  <Select value={defaultWorkflowId} onValueChange={(v) => v && setDefaultWorkflowId(v)}>
                    <SelectTrigger>
                      {defaultWorkflowId
                        ? <span className="truncate">
                            {candidates.find((c) => c.id === defaultWorkflowId)?.name ?? defaultWorkflowId}
                          </span>
                        : <SelectValue placeholder="选择一个 Workflow" />}
                    </SelectTrigger>
                    <SelectContent>
                      {candidates.map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    所有规则都未命中时派发到这个 Workflow。创建后可在"路由配置 → 规则表"
                    把其他场景路由到各自独立的 Workflow SOP。
                  </p>
                </>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" type="button" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button
              type="submit"
              disabled={
                !name.trim() ||
                loading ||
                (agentType === "orchestrator" && !defaultWorkflowId)
              }
            >
              {loading ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
