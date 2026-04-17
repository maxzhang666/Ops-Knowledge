import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { agentApi } from "@/api/agent"
import { streamChat, type SSEEvent } from "@/api/chat"

interface StepProps {
  onNext: () => void
  onBack?: () => void
}

export function StepTest({ onBack }: StepProps) {
  const navigate = useNavigate()
  const [query, setQuery] = useState("")
  const [answer, setAnswer] = useState("")
  const [loading, setLoading] = useState(false)
  const [agentId, setAgentId] = useState<string | null>(null)

  const handleTest = async () => {
    if (!query.trim()) return
    setLoading(true)
    setAnswer("")

    try {
      // Find first available agent
      let aid = agentId
      if (!aid) {
        const agents = await agentApi.list()
        if (agents.items.length === 0) {
          setAnswer("没有可用的智能体，请返回上一步创建。")
          setLoading(false)
          return
        }
        aid = agents.items[0].id
        setAgentId(aid)
      }

      let content = ""
      await streamChat(aid, query, undefined, (event: SSEEvent) => {
        if (event.event === "content_delta") {
          const data = typeof event.data === "string" ? JSON.parse(event.data) : event.data
          content += data.delta || ""
          setAnswer(content)
        }
      })
    } catch (e: any) {
      setAnswer(`Error: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>测试问答</CardTitle>
        <CardDescription>试试向智能体提问，验证系统是否正常工作</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex gap-2">
          <Input
            value={query}
            onChange={(e: any) => setQuery(e.target.value)}
            placeholder="输入问题..."
            onKeyDown={(e: any) => e.key === "Enter" && !loading && handleTest()}
            disabled={loading}
          />
          <Button onClick={handleTest} disabled={loading || !query.trim()}>
            {loading ? "回答中..." : "提问"}
          </Button>
        </div>

        {answer && (
          <div className="max-h-60 overflow-y-auto rounded-md border bg-muted/50 p-3 text-sm whitespace-pre-wrap">
            {answer}
          </div>
        )}

        <div className="flex gap-2">
          {onBack && <Button variant="outline" onClick={onBack}>上一步</Button>}
          <Button onClick={() => navigate("/login", { replace: true })} className="flex-1">
            进入系统
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
