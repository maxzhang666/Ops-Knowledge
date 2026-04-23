import { useCallback, useEffect, useRef, useState } from "react"
import { Chat, AIChatInput, Modal, TextArea } from "@douyinfe/semi-ui"
import type {
  Message as SemiMessage,
  RenderActionProps,
} from "@douyinfe/semi-ui/lib/es/chat/interface"
import { X, ListTree, Bot, UserCheck } from "lucide-react"

// AIChatInput 的 inputContents 是 TipTap JSON 节点；我们只关心 text 提取。
// 避免依赖 @douyinfe/semi-foundation 的子路径 import（不同 IDE tsconfig 解析不稳定）。
interface TiptapContent {
  type: string
  text?: string
  content?: TiptapContent[]
  [key: string]: unknown
}
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { workflowApi } from "@/api/workflow"
import { useEditorStore } from "./store"
import { connectExecutionEvents, type WsEvent } from "./ws"
import { flowToGraph } from "./dsl"


type MsgStatus = "loading" | "incomplete" | "complete" | "error"


/**
 * 画布内测试抽屉 — 基于 Semi `<Chat />`。
 *
 * Non-modal，仅 X 关闭。用户输入作为 `trigger_input.content` 发起工作流执行；
 * 每条 assistant 气泡绑定 `execution_id`，通过 `renderChatBoxAction` 注入
 * 「过程」按钮，打开节点级生成过程抽屉。
 */
interface Props {
  onClose: () => void
  onOpenProcess: (executionId: string) => void
}


export function TestChatDrawer({ onClose, onOpenProcess }: Props) {
  const workflow = useEditorStore((s) => s.workflow)
  const nodes = useEditorStore((s) => s.nodes)
  const edges = useEditorStore((s) => s.edges)
  const setWorkflow = useEditorStore((s) => s.setWorkflow)
  const markClean = useEditorStore((s) => s.markClean)
  const startExecution = useEditorStore((s) => s.startExecution)
  const recordNodeStatus = useEditorStore((s) => s.recordNodeStatus)
  const recordNodeOutput = useEditorStore((s) => s.recordNodeOutput)
  const recordNodeStart = useEditorStore((s) => s.recordNodeStart)
  const recordNodeEnd = useEditorStore((s) => s.recordNodeEnd)
  const appendStreamChunk = useEditorStore((s) => s.appendStreamChunk)
  const finishExecution = useEditorStore((s) => s.finishExecution)

  const [chats, setChats] = useState<SemiMessage[]>([])
  const [sending, setSending] = useState(false)
  // HITL 中断等待态。workflow_end(status=waiting) 到达后填入；
  // 用户在 Modal 里决定后清空并调 resumeExecution，随后重连 WS。
  const [interrupt, setInterrupt] = useState<{
    execId: string
    prompt: string
    approvers: string[]
    nodeId: string | null
  } | null>(null)
  const [decisionComment, setDecisionComment] = useState("")
  const [resumeSubmitting, setResumeSubmitting] = useState(false)
  const [resumeError, setResumeError] = useState<string | null>(null)
  const unsubRef = useRef<(() => void) | null>(null)
  // 测试会话的伪 conversation_id —— 保持稳定，模拟真实 chat 的 trigger_input。
  const testConversationIdRef = useRef<string>(crypto.randomUUID())

  useEffect(() => {
    return () => { unsubRef.current?.() }
  }, [])

  function updateAssistant(
    execId: string,
    updater: (m: SemiMessage) => SemiMessage,
  ) {
    setChats((prev) =>
      prev.map((m) =>
        m.role === "assistant" && m.execution_id === execId ? updater(m) : m,
      ),
    )
  }

  const handleEvent = useCallback(
    (execId: string) => (ev: WsEvent) => {
      const evTime = ev.ts ? Date.parse(ev.ts) || Date.now() : Date.now()
      if (ev.type === "node_start" && ev.node_id) {
        recordNodeStatus(ev.node_id, "running")
        recordNodeStart(ev.node_id, evTime)
      } else if (ev.type === "node_output" && ev.node_id) {
        if (ev.data.outputs !== undefined) recordNodeOutput(ev.node_id, ev.data.outputs)
      } else if (ev.type === "node_error" && ev.node_id) {
        recordNodeStatus(ev.node_id, "failed", String(ev.data.error ?? ""))
        recordNodeEnd(ev.node_id, evTime)
      } else if (ev.type === "node_end" && ev.node_id) {
        recordNodeStatus(ev.node_id, String(ev.data.status ?? "succeeded"))
        recordNodeEnd(ev.node_id, evTime)
      } else if (ev.type === "stream_chunk") {
        const delta = ev.data.delta as string | undefined
        if (delta) {
          appendStreamChunk(delta)
          updateAssistant(execId, (m) => ({
            ...m,
            content: (m.content as string ?? "") + delta,
          }))
        }
      } else if (ev.type === "waiting_input") {
        // HITL 暂停：后端 human_approval 节点调了 interrupt()，把首个
        // interrupt 填进 state 触发 Modal；workflow_end(status=waiting)
        // 紧随而至，走下面分支不再追加 content。
        const interrupts =
          (ev.data.interrupts as Array<{ id?: string; value?: Record<string, unknown> }>) ?? []
        const first = interrupts[0]?.value ?? {}
        const nodeId = (first.node_id as string | null) ?? null
        // LangGraph 节点通过 interrupt() 暂停时永不 return，updates 流里
        // 没有 node_start/node_end，画布 execStatus 不会被填入。这里拿到
        // node_id 后补一记 waiting，恢复 ring 视觉。
        if (nodeId) {
          recordNodeStart(nodeId, evTime)
          recordNodeStatus(nodeId, "waiting")
        }
        setInterrupt({
          execId,
          prompt: String(first.prompt ?? "请审批"),
          approvers: Array.isArray(first.approvers) ? (first.approvers as string[]) : [],
          nodeId,
        })
      } else if (ev.type === "workflow_end") {
        const rawStatus = String(ev.data.status ?? "succeeded")
        const status = mapStatus(rawStatus)
        finishExecution(rawStatus)
        // waiting：仅标记气泡为等待输入，节点输出在 resume 后通过同一 execId
        // 再次回流，不 getExecution 覆盖 content。
        if (rawStatus === "waiting") {
          updateAssistant(execId, (m) => ({
            ...m,
            status,
            content: m.content || "⏸ 等待人工审批…",
          }))
          return
        }
        const wfId = workflow?.id
        if (!wfId) {
          updateAssistant(execId, (m) => ({ ...m, status }))
          return
        }
        workflowApi.getExecution(wfId, execId)
          .then((detail) => {
            for (const n of detail.nodes) {
              recordNodeStatus(
                n.node_id, n.status,
                n.error ? String(n.error) : undefined,
              )
              if (n.output !== undefined && n.output !== null) {
                recordNodeOutput(n.node_id, n.output)
              }
            }
            const answer = pickAnswer(detail.nodes)
            updateAssistant(execId, (m) => ({
              ...m,
              status: detail.error ? "error" : status,
              content:
                detail.error ? String(detail.error)
                : answer ?? (m.content as string),
            }))
          })
          .catch(() => { /* best-effort */ })
      }
    },
    [
      workflow?.id,
      recordNodeStatus, recordNodeOutput, recordNodeStart, recordNodeEnd,
      appendStreamChunk, finishExecution,
    ],
  )

  async function handleSend(content: string) {
    const text = content.trim()
    if (!workflow || !text || sending) return
    const userId = crypto.randomUUID()
    const assistantId = crypto.randomUUID()
    setChats((prev) => [
      ...prev,
      { id: userId, role: "user", content: text, status: "complete", createAt: Date.now() },
      { id: assistantId, role: "assistant", content: "", status: "loading", createAt: Date.now() },
    ])
    setSending(true)
    try {
      // 测试前先把当前画布状态保存为最新草稿 —— from_draft=true 的执行读的是
      // 数据库里的 wf.graph_data，如果用户改了节点没手动保存，后端拿到的还是
      // 旧快照，会出现"改了没生效"的假象。
      const graph = flowToGraph(nodes, edges)
      const updated = await workflowApi.update(workflow.id, {
        graph_data: graph as unknown as Record<string, unknown>,
      })
      setWorkflow(updated)
      markClean()

      // 对齐真实 chat pipeline 的 trigger_input（见 app/chat/workflow_pipeline.py）：
      // content + conversation_id + history + metadata。测试场景只有最近一轮历史。
      const history = messagesToHistory(chats)
      const res = await workflowApi.run(
        workflow.id,
        {
          content: text,
          conversation_id: testConversationIdRef.current,
          history,
          metadata: {},
        },
        { from_draft: true },
      )
      startExecution(res.execution_id)
      setChats((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, execution_id: res.execution_id } : m,
        ),
      )
      unsubRef.current?.()
      unsubRef.current = connectExecutionEvents(
        workflow.id, res.execution_id, handleEvent(res.execution_id),
      )
    } catch (e) {
      const err = e instanceof Error ? e.message : "启动失败"
      toast.error(err)
      setChats((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, status: "error", content: err } : m,
        ),
      )
    } finally {
      setSending(false)
    }
  }

  const roleConfig = {
    user: { name: "我" },
    assistant: { name: "工作流", avatar: <Bot className="size-5" /> },
    system: { name: "系统" },
  }

  /** Semi Chat 的"重试"按钮回调 — 找到失败气泡前面那条 user 消息，
   *  把失败气泡及其后的全部删除，然后用相同文本重新发起执行。 */
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
    if (!text.trim()) return
    // 先截掉失败气泡及其后的消息，handleSend 会重新追加一对新气泡。
    setChats((p) => p.slice(0, idx - 1))
    handleSend(text)
  }

  /** 用户在 Modal 里点 批准/拒绝 → POST resume → 重连 WS 订阅后续事件。
   *  失败时 Modal 保留 + 展示错误 + 允许重试（再点批准/拒绝重发）。 */
  async function handleResume(decision: "approved" | "rejected") {
    if (!workflow || !interrupt || resumeSubmitting) return
    const { execId } = interrupt
    const comment = decisionComment.trim()
    const payload: Record<string, unknown> = { decision }
    if (comment) payload.comment = comment

    setResumeSubmitting(true)
    setResumeError(null)
    try {
      await workflowApi.resumeExecution(workflow.id, execId, payload)
      // 成功：关闭 Modal、落气泡、重连 WS。
      setInterrupt(null)
      setDecisionComment("")
      updateAssistant(execId, (m) => ({
        ...m,
        status: "loading",
        content: `${decision === "approved" ? "✅ 已批准" : "❌ 已拒绝"}${comment ? `：${comment}` : ""}\n\n继续执行…`,
      }))
      unsubRef.current?.()
      unsubRef.current = connectExecutionEvents(
        workflow.id, execId, handleEvent(execId),
      )
      startExecution(execId)
    } catch (e) {
      // 失败：Modal 不关，setResumeError 让用户看到错误并重试。
      const err = e instanceof Error ? e.message : "恢复失败"
      setResumeError(err)
      toast.error(err)
    } finally {
      setResumeSubmitting(false)
    }
  }

  function closeResumeModal() {
    if (resumeSubmitting) return  // 请求中不允许关
    setInterrupt(null)
    setDecisionComment("")
    setResumeError(null)
  }

  const chatBoxRenderConfig = {
    renderChatBoxAction: (props: RenderActionProps) => {
      const msg = props.message
      const execId = (msg?.execution_id as string | undefined) ?? undefined
      if (msg?.role !== "assistant" || !execId || msg.status === "loading") {
        return props.defaultActions
      }
      return (
        <div className={props.className}>
          <button
            type="button"
            onClick={() => onOpenProcess(execId)}
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] hover:bg-muted"
            title="查看节点级生成过程"
          >
            <ListTree className="size-3" /> 过程
          </button>
          {props.defaultActions}
        </div>
      )
    },
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="text-sm font-medium">测试对话</div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={() => setChats([])}
            title="清空对话"
          >
            <ListTree className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={onClose}
            title="关闭（不影响画布）"
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>

      {/* Chat 内部的消息列表和 AIChatInput 默认会铺满父容器；加 padding
          让它们与卡片圆角边界之间留出呼吸感。 */}
      <div className="min-h-0 flex-1 px-2 pb-2">
        <Chat
          chats={chats}
          onChatsChange={(next) => setChats(next ?? [])}
          roleConfig={roleConfig}
          align="leftRight"
          mode="bubble"
          escapeHtml={false}
          showStopGenerate={false}
          showClearContext={false}
          sendHotKey="enter"
          placeholder="输入消息 — 作为 trigger_input.content 传给工作流"
          onMessageSend={handleSend}
          onMessageReset={handleReset}
          chatBoxRenderConfig={chatBoxRenderConfig}
          // 使用 Semi AIChatInput 作为输入区，代替 Chat 默认 textarea。
          // 它基于 TipTap，支持富文本、@提及、附件扩展等能力（当前场景先关闭这些）。
          renderInputArea={() => (
            <AIChatInput
              placeholder="输入消息 — 作为 trigger_input.content 传给工作流"
              showUploadButton={false}
              showUploadFile={false}
              showReference={false}
              canSend={!sending}
              generating={sending}
              keepSkillAfterSend={false}
              // 直接调 handleSend；不走 Chat 的 onSend 链路，否则 Chat 会先
              // 通过 onChatsChange 追加一条 user 消息，再加上 handleSend 里
              // 自己追加的 user，导致记录里出现 2 条相同消息。
              onMessageSend={(msg) => {
                const text = extractText(msg.inputContents)
                if (text) handleSend(text)
              }}
            />
          )}
        />
      </div>

      <Modal
        visible={!!interrupt}
        title={
          <div className="flex items-center gap-2 text-sm">
            <UserCheck className="size-4 text-orange-600" />
            人工审批
          </div>
        }
        onCancel={closeResumeModal}
        maskClosable={!resumeSubmitting}
        footer={
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={resumeSubmitting}
              onClick={() => handleResume("rejected")}
            >
              {resumeSubmitting ? "提交中…" : resumeError ? "重试拒绝" : "拒绝"}
            </Button>
            <Button
              size="sm"
              disabled={resumeSubmitting}
              onClick={() => handleResume("approved")}
            >
              {resumeSubmitting ? "提交中…" : resumeError ? "重试批准" : "批准"}
            </Button>
          </div>
        }
        closeOnEsc={!resumeSubmitting}
      >
        {interrupt && (
          <div className="space-y-3 text-sm">
            <div className="rounded bg-muted/40 p-3 whitespace-pre-wrap break-words">
              {interrupt.prompt}
            </div>
            {interrupt.approvers.length > 0 && (
              <div className="text-xs text-muted-foreground">
                审批人：{interrupt.approvers.join("、")}
              </div>
            )}
            <TextArea
              placeholder="备注（可选）"
              value={decisionComment}
              onChange={(v) => setDecisionComment(v)}
              rows={3}
              autosize={{ minRows: 2, maxRows: 6 }}
              disabled={resumeSubmitting}
            />
            {resumeError && (
              <div className="rounded bg-red-50 px-2 py-1.5 text-xs text-red-900 dark:bg-red-950 dark:text-red-200">
                提交失败：{resumeError}。修改后再点批准 / 拒绝重试。
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}


/** 把 Semi Chat 的消息数组转成 workflow pipeline 期望的 history 结构 */
function messagesToHistory(
  chats: SemiMessage[],
): Array<{ role: string; content: string }> {
  return chats
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.status !== "loading")
    .map((m) => ({
      role: m.role as string,
      content:
        typeof m.content === "string"
          ? m.content
          : Array.isArray(m.content)
            ? m.content.map((c) => (c as { text?: string }).text ?? "").join("")
            : "",
    }))
}


/** AIChatInput.onMessageSend 的 `inputContents` 是 TipTap JSON；递归提取纯文本。 */
function extractText(contents?: TiptapContent[]): string {
  if (!contents || contents.length === 0) return ""
  let out = ""
  for (const c of contents) {
    if (c.type === "text" && typeof c.text === "string") out += c.text
    if (Array.isArray(c.content)) out += extractText(c.content)
  }
  return out.trim()
}


function mapStatus(s: string): MsgStatus {
  if (s === "succeeded") return "complete"
  if (s === "failed") return "error"
  if (s === "cancelled") return "incomplete"
  if (s === "waiting") return "incomplete"  // resume 后再更新成 complete
  return "complete"
}


function pickAnswer(
  nodes: Array<{ node_id: string; type: string; output: Record<string, unknown> | null }>,
): string | undefined {
  for (const n of nodes) {
    if (n.type === "answer" && n.output && typeof n.output.answer === "string") {
      return n.output.answer
    }
  }
  for (const n of nodes) {
    if (n.output && typeof n.output.content === "string") {
      return n.output.content as string
    }
  }
  return undefined
}
