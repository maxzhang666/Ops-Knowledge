import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { agentApi, type Agent } from "@/api/agent"

interface AgentConfigFormProps {
  agent: Agent
  onUpdated: () => void
}

export function AgentConfigForm({ agent, onUpdated }: AgentConfigFormProps) {
  const [systemPrompt, setSystemPrompt] = useState(agent.system_prompt)
  const [welcomeMessage, setWelcomeMessage] = useState(agent.welcome_message)
  const [enableThinking, setEnableThinking] = useState(agent.enable_thinking)
  const [loading, setLoading] = useState(false)

  async function handleSave() {
    setLoading(true)
    try {
      await agentApi.update(agent.id, {
        system_prompt: systemPrompt,
        welcome_message: welcomeMessage,
        enable_thinking: enableThinking,
      })
      onUpdated()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mt-4 flex max-w-2xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Label htmlFor="system-prompt">系统提示词</Label>
        <Textarea
          id="system-prompt"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          placeholder="定义智能体的行为和角色"
          rows={6}
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="welcome-msg">欢迎消息</Label>
        <Input
          id="welcome-msg"
          value={welcomeMessage}
          onChange={(e) => setWelcomeMessage(e.target.value)}
          placeholder="用户打开对话时的欢迎消息"
        />
      </div>

      <div className="flex items-center gap-3">
        <Switch
          id="enable-thinking"
          checked={enableThinking}
          onCheckedChange={(v) => setEnableThinking(v as boolean)}
        />
        <Label htmlFor="enable-thinking">启用思维链</Label>
      </div>

      <div>
        <Button onClick={handleSave} disabled={loading}>
          {loading ? "保存中..." : "保存配置"}
        </Button>
      </div>
    </div>
  )
}
