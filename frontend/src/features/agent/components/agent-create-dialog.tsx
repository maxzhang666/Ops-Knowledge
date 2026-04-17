import { useState } from "react"
import { useNavigate } from "react-router-dom"
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

const agentTypeOptions: { value: AgentType; label: string; disabled: boolean; badge?: string }[] = [
  { value: "simple", label: "简易智能体", disabled: false },
  { value: "workflow", label: "工作流智能体", disabled: true, badge: "Phase 1b" },
  { value: "orchestrator", label: "编排智能体", disabled: true, badge: "Phase 2" },
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
      const agent = await agentApi.create({
        name: name.trim(),
        description: description.trim() || undefined,
        agent_type: agentType,
      })
      reset()
      onOpenChange(false)
      onCreated()
      // Agent Workbench uses ?menu=xxx (not ?tab=). Default menu is "persona"
      // which is exactly where a freshly-created agent should land.
      navigate(`/agents/${agent.id}`)
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
