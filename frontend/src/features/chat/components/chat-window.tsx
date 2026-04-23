import { useCallback, useEffect, useMemo, useState } from "react"
import { Chat, AIChatInput } from "@douyinfe/semi-ui"
import type { Message as SemiMessage } from "@douyinfe/semi-ui/lib/es/chat/interface"
import { Bot } from "lucide-react"

// AIChatInput.onMessageSend 的 inputContents 是 TipTap JSON 节点；只取 text。
interface TiptapContent {
  type: string
  text?: string
  content?: TiptapContent[]
  [key: string]: unknown
}
import { ReferencePanel } from "./reference-panel"
import { sendMessage, abortStream } from "./sse-handler"
import { useChatStore } from "@/stores/chat"
import { chatApi, type Message as ApiMessage } from "@/api/chat"
import { markdownCodeBlockComponents } from "@/components/shared/markdown-code-block"

interface ChatWindowProps {
  agentId: string
  conversationId: string | null
  welcomeMessage?: string
  /** 快捷提问：空会话时展示为可点击的 hint chips。 */
  suggestedQuestions?: string[]
  /** Plan 31: 驱动 Orchestrator 专属的诊断模式按钮。非 orchestrator 忽略。 */
  agentType?: string
}

/**
 * Chat 窗口 — 基于 Semi `<Chat />`。
 *
 * Semi Chat 内置：
 *  - 气泡渲染（MarkdownRender 自动集成）
 *  - 消息操作（复制/点赞/点踩/重生成/删除）
 *  - 滚动锚定 / 返回底部 / 输入热键
 *  - 思维链 → 融合到 loading 态气泡（prefix 引用块）
 *
 * 我们仍然维护：
 *  - Citation 跳转：`[N]` → <sup data-cite="N">，通过 customMarkDownComponents.sup
 *    拦截 data-cite 属性直接挂 onClick，打开右侧 ReferencePanel
 *  - AIChatInput 替代默认 textarea（附件/引用先关闭），onStopGenerate 绑 abortStream
 *  - conversationId 加载历史（getMessages）
 */
export function ChatWindow({ agentId, conversationId, welcomeMessage, suggestedQuestions, agentType }: ChatWindowProps) {
  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const pendingContent = useChatStore((s) => s.pendingContent)
  const thinkingSteps = useChatStore((s) => s.thinkingSteps)
  const retrievalResults = useChatStore((s) => s.retrievalResults)
  const setMessages = useChatStore((s) => s.setMessages)
  const orchestratorDecision = useChatStore((s) => s.orchestratorDecision)
  const handlerInvoked = useChatStore((s) => s.handlerInvoked)

  const [refOpen, setRefOpen] = useState(false)
  const [refHighlight, setRefHighlight] = useState<number | undefined>()
  const [debugMode, setDebugMode] = useState(false)
  const isOrchestrator = agentType === "orchestrator"

  const loadMessages = useCallback(async () => {
    if (!conversationId) {
      setMessages([])
      return
    }
    const res = await chatApi.getMessages(agentId, conversationId, { page_size: "100" })
    const list = Array.isArray(res) ? res : (res as { items?: ApiMessage[] }).items ?? []
    setMessages(list)
  }, [agentId, conversationId, setMessages])

  // 流式进行中不重载历史，避免覆盖流中状态
  useEffect(() => {
    if (isStreaming) return
    loadMessages()
  }, [loadMessages, isStreaming])

  useEffect(() => {
    return () => { abortStream() }
  }, [])

  const chats: SemiMessage[] = useMemo(() => {
    const out: SemiMessage[] = messages.map(toSemi)
    if (isStreaming) {
      const prefix = thinkingSteps.length > 0
        ? `> 🧠 **思维链**（${thinkingSteps.length} 步）\n\n${thinkingSteps
            .map((t) => `> - ${t.content}`)
            .join("\n")}\n\n`
        : ""
      out.push({
        id: "__streaming__",
        role: "assistant",
        content: prefix + injectCitations(pendingContent),
        status: "loading",
        createAt: Date.now(),
      })
    }
    return out
  }, [messages, isStreaming, pendingContent, thinkingSteps])

  const roleConfig = useMemo(
    () => ({
      user: { name: "我" },
      assistant: {
        name: "助手",
        avatar: <Bot className="size-5" />,
      },
      system: { name: "系统" },
    }),
    [],
  )

  function handleSend(content: string) {
    if (!content.trim()) return
    sendMessage(agentId, content.trim(), conversationId ?? undefined, {
      debug: isOrchestrator && debugMode,
    })
  }

  function handleStop() {
    abortStream()
  }

  /** 重试：找到失败气泡前一条 user 消息，重新发送一次。 */
  function handleReset(msg?: SemiMessage) {
    if (!msg || msg.role !== "assistant") return
    const idx = chats.findIndex((c) => c.id === msg.id)
    if (idx < 1) return
    const prev = chats[idx - 1]
    if (prev.role !== "user") return
    const text =
      typeof prev.content === "string"
        ? prev.content
        : Array.isArray(prev.content)
          ? prev.content.map((c) => c.text ?? "").join("")
          : ""
    if (text.trim()) handleSend(text)
  }

  // customMarkDownComponents 叠加两项：
  //  - sup：data-cite 属性拦截为可点击引用，其他（H<sup>2</sup>O）原样
  //  - pre：代码块加 hover 复制按钮（来自公共组件）
  const customMarkDownComponents = useMemo(() => ({
    ...markdownCodeBlockComponents,
    sup: (
      props: React.HTMLAttributes<HTMLElement> & { "data-cite"?: string | number },
    ) => {
      const cite = props["data-cite"]
      if (cite === undefined || cite === null || cite === "") {
        return <sup {...props} />
      }
      const idx = Number(cite)
      return (
        <sup
          className="citation-ref mx-0.5 cursor-pointer text-[10px] text-blue-600 hover:underline"
          role="button"
          tabIndex={0}
          onClick={() => {
            if (!Number.isNaN(idx)) {
              setRefHighlight(idx)
              setRefOpen(true)
            }
          }}
        >
          {props.children}
        </sup>
      )
    },
  }), [])

  const showWelcome = !isStreaming && messages.length === 0 && !!welcomeMessage
  const activeRetrievalResults = isStreaming ? retrievalResults : []
  // Hints 仅在空会话时展示；流式或已有对话不再打扰用户。
  const activeHints =
    !isStreaming && messages.length === 0
      ? (suggestedQuestions ?? []).filter((q) => q.trim())
      : []

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {isOrchestrator && (
        <div className="flex items-center justify-between border-b bg-muted/30 px-3 py-1.5 text-xs">
          <span className="text-muted-foreground">编排智能体 · 按规则派发到下游</span>
          <label className="flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={debugMode}
              onChange={(e) => setDebugMode(e.target.checked)}
              className="size-3.5"
            />
            <span>诊断模式（展示路由决策）</span>
          </label>
        </div>
      )}
      {isOrchestrator && debugMode && (orchestratorDecision || handlerInvoked) && (
        <div className="border-b bg-amber-50/40 px-3 py-1.5 text-[11px]">
          {orchestratorDecision?.matched_rule ? (
            <span>
              命中规则 <span className="font-mono">{orchestratorDecision.matched_rule.id.slice(0, 8)}</span>
              （{orchestratorDecision.matched_rule.match_type}）
              → <span className="font-medium">{orchestratorDecision.matched_rule.handler_type}</span>
            </span>
          ) : (
            <span className="text-muted-foreground">无匹配，走默认 handler</span>
          )}
          {orchestratorDecision?.classifier && (
            <span className="ml-2 text-muted-foreground">
              · classifier: {orchestratorDecision.classifier.category}
              （conf {orchestratorDecision.classifier.confidence.toFixed(2)}
              {orchestratorDecision.classifier.cached ? ", cached" : ""}）
            </span>
          )}
          {orchestratorDecision?.tried_rules && orchestratorDecision.tried_rules.length > 0 && (
            <span className="ml-2 text-muted-foreground">
              · 尝试过 {orchestratorDecision.tried_rules.length} 条规则
            </span>
          )}
          {handlerInvoked && (
            <span className="ml-2 text-muted-foreground">
              · handler_id: <span className="font-mono">{handlerInvoked.handler_id?.slice(0, 8) ?? "-"}</span>
            </span>
          )}
        </div>
      )}
      <div className="chat-root min-h-0 flex-1">
        <Chat
          chats={chats}
          roleConfig={roleConfig}
          align="leftRight"
          mode="bubble"
          escapeHtml={false}
          showStopGenerate={false}
          showClearContext={false}
          onMessageSend={handleSend}
          onMessageReset={handleReset}
          customMarkDownComponents={customMarkDownComponents}
          hints={activeHints.length > 0 ? activeHints : undefined}
          onHintClick={handleSend}
          topSlot={
            showWelcome ? (
              <div className="flex flex-col items-center gap-3 py-12 text-center">
                <Bot className="size-10 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">{welcomeMessage}</p>
              </div>
            ) : null
          }
          // AIChatInput 取代默认 textarea；流式时显示 stop 按钮（generating=true）。
          // 通过 onMessageSend → handleSend 触发发送，与 test-chat-drawer 保持一致。
          renderInputArea={() => (
            <AIChatInput
              placeholder="输入消息，Enter 发送，Shift+Enter 换行"
              showUploadButton={false}
              showUploadFile={false}
              showReference={false}
              canSend={!isStreaming}
              generating={isStreaming}
              keepSkillAfterSend={false}
              onMessageSend={(msg) => {
                const text = extractText(msg.inputContents)
                if (text) handleSend(text)
              }}
              onStopGenerate={handleStop}
            />
          )}
        />
      </div>

      <ReferencePanel
        open={refOpen}
        onOpenChange={setRefOpen}
        chunks={activeRetrievalResults}
        highlightIndex={refHighlight}
      />
    </div>
  )
}


/** 把 `[N]` 引用符号包进 <sup data-cite="N">；样式/点击由 customMarkDownComponents 接管。 */
function injectCitations(content: string): string {
  return content.replace(/\[(\d+)\]/g, (_, n) => `<sup data-cite="${n}">[${n}]</sup>`)
}


/** AIChatInput 的 inputContents 是 TipTap JSON；递归提取纯文本。 */
function extractText(contents?: TiptapContent[]): string {
  if (!contents || contents.length === 0) return ""
  let out = ""
  for (const c of contents) {
    if (c.type === "text" && typeof c.text === "string") out += c.text
    if (Array.isArray(c.content)) out += extractText(c.content)
  }
  return out.trim()
}


function toSemi(m: ApiMessage): SemiMessage {
  return {
    id: m.id,
    role: m.role,
    content: m.role === "assistant" ? injectCitations(m.content) : m.content,
    status:
      m.status === "generating" ? "loading"
      : m.status === "error" ? "error"
      : "complete",
    createAt: new Date(m.created_at).getTime(),
  }
}
