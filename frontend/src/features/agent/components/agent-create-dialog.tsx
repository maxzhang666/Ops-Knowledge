import { useState } from "react"
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
import { agentApi, type AgentType } from "@/api/agent"
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

  function reset() {
    setName("")
    setDescription("")
    setAgentType("simple")
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return

    setLoading(true)
    try {
      const payload: Parameters<typeof agentApi.create>[0] = {
        name: name.trim(),
        description: description.trim() || undefined,
        agent_type: agentType,
      }
      if (agentType === "orchestrator") {
        // 后端 create_agent 对 orchestrator 自动建一个 "默认 SOP" Workflow
        // 并填入 orchestrator_config.default_handler；前端只需提示一下
        // trusted paths / diag roles（这些字段可在 workbench 修改）。
        payload.orchestrator_config = {
          trusted_metadata_paths: ["user.role", "user.department_id", "user.id"],
          diagnostic_mode_allowed_roles: ["system_admin", "dept_admin"],
          classifier: null,
          // default_handler 故意留空 —— 后端识别后自动建 Workflow 并回填。
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
            <p className="rounded-md border border-dashed bg-muted/30 p-2 text-xs text-muted-foreground">
              将自动创建一个"默认 SOP"工作流（作为兜底 handler），创建后可在
              智能体页面内的"SOP 流程"菜单新增更多独立 SOP，并在"规则表"配置路由。
            </p>
          )}
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
