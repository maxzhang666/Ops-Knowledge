import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { knowledgeApi } from "@/api/knowledge"
import { agentApi } from "@/api/agent"

interface StepProps {
  onNext: () => void
  onBack?: () => void
}

export function StepKnowledge({ onNext, onBack }: StepProps) {
  const [kbName, setKbName] = useState("")
  const [kbDesc, setKbDesc] = useState("")
  const [agentName, setAgentName] = useState("")
  const [agentDesc, setAgentDesc] = useState("")
  const [loading, setLoading] = useState(false)
  const [created, setCreated] = useState(false)

  const handleCreate = async () => {
    if (!kbName) {
      toast.error("Please enter a knowledge base name")
      return
    }
    setLoading(true)
    try {
      const kb = await knowledgeApi.createKB({ name: kbName, description: kbDesc || undefined })
      toast.success(`Knowledge base "${kb.name}" created`)

      if (agentName) {
        await agentApi.create({
          name: agentName,
          description: agentDesc || undefined,
          agent_type: "simple",
          knowledge_base_ids: [kb.id],
        })
        toast.success(`Agent "${agentName}" created`)
      }
      setCreated(true)
    } catch (e: any) {
      toast.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>创建知识库与智能体</CardTitle>
        <CardDescription>创建你的第一个知识库，并关联一个智能体</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="space-y-3">
          <h3 className="text-sm font-medium">知识库</h3>
          <div>
            <Label>名称</Label>
            <Input value={kbName} onChange={(e: any) => setKbName(e.target.value)} placeholder="e.g. 运维知识库" disabled={created} />
          </div>
          <div>
            <Label>描述</Label>
            <Input value={kbDesc} onChange={(e: any) => setKbDesc(e.target.value)} placeholder="Optional" disabled={created} />
          </div>

          <h3 className="mt-4 text-sm font-medium">智能体（可选）</h3>
          <div>
            <Label>名称</Label>
            <Input value={agentName} onChange={(e: any) => setAgentName(e.target.value)} placeholder="e.g. 运维助手" disabled={created} />
          </div>
          <div>
            <Label>描述</Label>
            <Input value={agentDesc} onChange={(e: any) => setAgentDesc(e.target.value)} placeholder="Optional" disabled={created} />
          </div>
        </div>

        {created && <p className="text-sm text-green-600">创建成功！可在下一步测试问答，或直接进入系统。</p>}

        <div className="flex gap-2">
          {onBack && <Button variant="outline" onClick={onBack}>上一步</Button>}
          {!created ? (
            <>
              <Button variant="outline" onClick={handleCreate} disabled={!kbName || loading}>
                {loading ? "创建中..." : "创建"}
              </Button>
              <Button onClick={onNext} className="flex-1">跳过</Button>
            </>
          ) : (
            <Button onClick={onNext} className="flex-1">下一步</Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
