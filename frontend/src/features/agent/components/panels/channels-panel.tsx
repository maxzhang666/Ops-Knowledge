import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Copy, KeyRound, ExternalLink, Play } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/api/client"
import type { Agent } from "@/api/agent"

interface ChatReply {
  conversation_id?: string
  message_id?: string
  answer?: string
  token_usage?: Record<string, number>
  references?: unknown[]
}

/**
 * Channels panel — spec 04 §46 / spec 22 §5.
 *
 * Phase 1b scope: surface the four Agent-chat API calling modes + an API Key
 * quick-entry. Embed Widget (iframe / <script>) lands in Phase 2 per spec
 * 19 §5, so that tile stays as a disabled placeholder.
 */
export function ChannelsPanel({ agent }: { agent: Agent }) {
  const navigate = useNavigate()
  const base = window.location.origin
  const endpoint = `${base}/api/v1/agents/${agent.id}/chat`

  function copy(text: string) {
    navigator.clipboard.writeText(text)
      .then(() => toast.success("已复制"))
      .catch(() => toast.error("复制失败"))
  }

  const examples = useMemo(() => buildExamples(endpoint), [endpoint])
  const [activeTab, setActiveTab] = useState<keyof typeof examples>("sse")

  // In-page live test — both blocking and SSE paths supported so users can
  // verify their preferred integration without leaving the page.
  const [testMsg, setTestMsg] = useState("你好，请自我介绍")
  const [testMode, setTestMode] = useState<"blocking" | "sse">("blocking")
  const [testing, setTesting] = useState(false)
  const [streamText, setStreamText] = useState("")
  const [testResult, setTestResult] = useState<
    | { status: "ok"; reply: ChatReply }
    | { status: "stream_done" }
    | { status: "error"; code: number | null; detail: string }
    | null
  >(null)

  async function handleTest() {
    setTesting(true)
    setTestResult(null)
    setStreamText("")

    if (testMode === "blocking") {
      try {
        const reply = await api.post<ChatReply>(
          `/agents/${agent.id}/chat`,
          { content: testMsg },
          { Accept: "application/json" },
        )
        setTestResult({ status: "ok", reply })
      } catch (e) {
        const status = (e as { status?: number } | null)?.status ?? null
        const detail = e instanceof Error ? e.message : String(e)
        setTestResult({ status: "error", code: status, detail: detail.slice(0, 600) })
      } finally {
        setTesting(false)
      }
      return
    }

    // SSE — fetch() streams response body. EventSource doesn't allow POST,
    // so we parse SSE frames (event:/data:) manually.
    try {
      const token = localStorage.getItem("access_token") ?? ""
      const res = await fetch(`/api/v1/agents/${agent.id}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "text/event-stream",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({ content: testMsg }),
      })
      if (!res.ok || !res.body) {
        const txt = await res.text().catch(() => "")
        setTestResult({
          status: "error", code: res.status,
          detail: txt.slice(0, 600) || res.statusText,
        })
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ""
      let currentEvent = ""
      let accumulated = ""

      while (true) {
        const { value: chunk, done } = await reader.read()
        if (done) break
        buf += decoder.decode(chunk, { stream: true })
        let sep = buf.indexOf("\n\n")
        while (sep !== -1) {
          const frame = buf.slice(0, sep)
          buf = buf.slice(sep + 2)
          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) {
              currentEvent = line.slice(6).trim()
            } else if (line.startsWith("data:")) {
              const data = line.slice(5).trim()
              if (currentEvent === "content_delta") {
                try {
                  const obj = JSON.parse(data)
                  if (typeof obj.delta === "string") {
                    accumulated += obj.delta
                    setStreamText(accumulated)
                  }
                } catch {
                  // drop malformed frame
                }
              }
            }
          }
          sep = buf.indexOf("\n\n")
        }
      }
      setTestResult({ status: "stream_done" })
    } catch (e) {
      setTestResult({
        status: "error", code: null,
        detail: (e instanceof Error ? e.message : String(e)).slice(0, 600),
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4 text-sm">
      <div>
        <h2 className="text-base font-semibold">渠道</h2>
        <p className="text-xs text-muted-foreground">
          通过 API、Webhook 或嵌入组件向外部系统暴露该智能体。
        </p>
      </div>

      {/* API access ------------------------------------------------------- */}
      <Card className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">API 访问</div>
            <div className="text-xs text-muted-foreground">
              四种调用模式共用同一端点，通过 Header 切换
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate("/settings/api-keys")}>
            <KeyRound className="mr-1 size-3.5" /> 管理 API Key
          </Button>
        </div>
        <div>
          <Label className="text-xs">
            端点 URL <span className="text-muted-foreground">（仅 POST，浏览器 GET 会返回 405）</span>
          </Label>
          <div className="flex gap-1">
            <input
              readOnly
              value={endpoint}
              onFocus={(e) => e.currentTarget.select()}
              className="flex-1 rounded-md border border-input bg-background px-2 py-1 font-mono text-xs"
            />
            <Button size="icon" variant="outline" className="size-8" onClick={() => copy(endpoint)}>
              <Copy className="size-3.5" />
            </Button>
          </div>
        </div>

        {/* Live test — actually POST with the current session JWT so users
            can verify end-to-end without crafting a cURL command. */}
        <div className="rounded-md border bg-muted/30 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <Label className="text-xs font-medium">立即测试（使用当前登录会话）</Label>
            <div className="flex gap-1">
              <Button
                size="sm" className="h-7 text-xs"
                variant={testMode === "blocking" ? "default" : "outline"}
                onClick={() => setTestMode("blocking")}
                disabled={testing}
              >
                Blocking
              </Button>
              <Button
                size="sm" className="h-7 text-xs"
                variant={testMode === "sse" ? "default" : "outline"}
                onClick={() => setTestMode("sse")}
                disabled={testing}
              >
                SSE
              </Button>
              <Button size="sm" onClick={handleTest} disabled={testing || !testMsg.trim()}>
                <Play className="mr-1 size-3" />
                {testing ? "请求中..." : "发送"}
              </Button>
            </div>
          </div>
          <Input
            value={testMsg}
            onChange={(e) => setTestMsg(e.target.value)}
            placeholder="测试消息"
            className="h-8 text-xs"
          />
          {testMode === "sse" && (streamText || testing) && (
            <div className="mt-2 rounded bg-background p-2 text-xs">
              <div className="mb-1 text-blue-600 dark:text-blue-400">
                ⇄ SSE 流 {testResult?.status === "stream_done" ? "· 完成" : "· 接收中..."}
              </div>
              <div className="whitespace-pre-wrap font-mono">
                {streamText || "（等待 content_delta...）"}
              </div>
            </div>
          )}
          {testMode === "blocking" && testResult?.status === "ok" && (
            <div className="mt-2 rounded bg-background p-2 text-xs">
              <div className="mb-1 text-green-700 dark:text-green-400">
                ✓ 请求成功 (200)
              </div>
              <div className="whitespace-pre-wrap">
                {testResult.reply.answer ?? "（无回复内容）"}
              </div>
              {testResult.reply.token_usage && (
                <div className="mt-1 text-muted-foreground">
                  tokens: in {testResult.reply.token_usage.input_tokens ?? 0} /
                  out {testResult.reply.token_usage.output_tokens ?? 0}
                </div>
              )}
            </div>
          )}
          {testResult?.status === "error" && (
            <div className="mt-2 rounded bg-background p-2 text-xs">
              <div className="mb-1 text-destructive">
                ✗ 请求失败 {testResult.code !== null && `(${testResult.code})`}
              </div>
              <div className="whitespace-pre-wrap text-muted-foreground">
                {testResult.detail || "未知错误"}
              </div>
            </div>
          )}
        </div>

        <div>
          <div className="mb-1 flex gap-1">
            {(Object.keys(examples) as Array<keyof typeof examples>).map((k) => (
              <Button
                key={k}
                variant={activeTab === k ? "default" : "outline"}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setActiveTab(k)}
              >
                {examples[k].label}
              </Button>
            ))}
          </div>
          <Textarea
            readOnly
            rows={8}
            className="font-mono text-[11px]"
            value={examples[activeTab].snippet}
          />
          <div className="mt-1 flex justify-between text-xs text-muted-foreground">
            <span>{examples[activeTab].hint}</span>
            <button
              type="button"
              className="underline"
              onClick={() => copy(examples[activeTab].snippet)}
            >
              复制
            </button>
          </div>
        </div>
      </Card>

      {/* Embed widget placeholder ---------------------------------------- */}
      <Card className="space-y-2 p-4 opacity-70">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">嵌入组件</div>
            <div className="text-xs text-muted-foreground">
              iframe / &lt;script&gt; 两种嵌入方式
            </div>
          </div>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase">
            Phase 2
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          将在 Phase 2 开放。届时可在网站中以一行脚本嵌入智能体对话窗。
        </p>
      </Card>

      {/* External webhook placeholder ------------------------------------- */}
      <Card className="space-y-2 p-4 opacity-70">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">外部 Webhook</div>
            <div className="text-xs text-muted-foreground">
              系统事件订阅（document.completed 等）推送到外部 URL
            </div>
          </div>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase">
            Phase 2
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          工作流智能体的入口 Webhook 已在工作流编辑器中配置；此处预留的 Outbound
          Webhook（系统向外推送事件）在 Phase 2 开放。
        </p>
      </Card>

      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <ExternalLink className="size-3" />
        四种调用模式详见 spec 22 §5 / Agent Chat API。
      </p>
    </div>
  )
}


function pollingUrl(endpoint: string) {
  // Chat endpoint is /agents/{id}/chat; polling hits /agents/{id}/messages/{msg}.
  return endpoint.replace(/\/chat$/, "/messages/<MESSAGE_ID>")
}

function buildExamples(endpoint: string) {
  const apiKeyPlaceholder = "<YOUR_API_KEY>"
  return {
    sse: {
      label: "Sync SSE (前端)",
      hint: "默认浏览器 SSE 流式返回",
      snippet: `curl -N -H "Authorization: Bearer ${apiKeyPlaceholder}" \\
     -H "Accept: text/event-stream" \\
     -H "Content-Type: application/json" \\
     -d '{"content": "你好"}' \\
     ${endpoint}`,
    },
    blocking: {
      label: "Sync Blocking",
      hint: "等待完整回复，返回 JSON",
      snippet: `curl -H "Authorization: Bearer ${apiKeyPlaceholder}" \\
     -H "Accept: application/json" \\
     -H "Content-Type: application/json" \\
     -d '{"content": "你好"}' \\
     ${endpoint}`,
    },
    async_callback: {
      label: "Async + Callback",
      hint: "立即返回 202 + 异步 POST 到回调 URL",
      snippet: `curl -H "Authorization: Bearer ${apiKeyPlaceholder}" \\
     -H "Content-Type: application/json" \\
     -d '{"content": "你好", "async": true, "callback_url": "https://your.app/webhook"}' \\
     ${endpoint}`,
    },
    async_poll: {
      label: "Async + Polling",
      hint: "立即返回 202，通过 GET /messages/{id} 轮询",
      snippet: `# 1) kick off
curl -H "Authorization: Bearer ${apiKeyPlaceholder}" \\
     -H "Content-Type: application/json" \\
     -d '{"content": "你好", "async": true}' \\
     ${endpoint}

# 2) poll (message_id returned in step 1)
curl -H "Authorization: Bearer ${apiKeyPlaceholder}" \\
     ${pollingUrl(endpoint)}`,
    },
  } as const
}
