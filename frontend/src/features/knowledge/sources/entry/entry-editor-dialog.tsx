import { useEffect, useMemo, useState } from "react"
import MDEditor from "@uiw/react-md-editor"
import { toast } from "sonner"
import { Check, ChevronDown, ChevronRight, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { TimeDisplay } from "@/components/shared/time-display"
import { entryApi, type KnowledgeEntry } from "@/api/entry"
import { type Folder } from "@/api/knowledge"
import { useTheme } from "@/hooks/use-theme"
import { cn } from "@/lib/utils"

const ROOT_FOLDER_VALUE = "__root__"  // Select 不能传 null/空字符串

// 把 folder 树扁平化为 [{id, label, depth}] 列表，label 含缩进体现层级
function flattenFolders(folders: Folder[], depth = 0): { id: string; label: string }[] {
  const out: { id: string; label: string }[] = []
  for (const f of folders) {
    const prefix = "　".repeat(depth)
    out.push({ id: f.id, label: prefix + f.name })
    if (f.children && f.children.length > 0) {
      out.push(...flattenFolders(f.children, depth + 1))
    }
  }
  return out
}

// 倒推目标 folderId 在文件树中的祖先链；找不到 / NULL 返回 []（即根目录）
function buildFolderPath(folders: Folder[], folderId: string | null): string[] {
  if (!folderId) return []
  const result: string[] = []
  function dfs(nodes: Folder[], ancestors: string[]): boolean {
    for (const n of nodes) {
      const next = [...ancestors, n.name]
      if (n.id === folderId) {
        result.push(...next)
        return true
      }
      if (n.children && n.children.length > 0 && dfs(n.children, next)) return true
    }
    return false
  }
  dfs(folders, [])
  return result
}

// ────────────────────────────────────────────────────────────────
// 右侧信息面板小组件

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-sm font-semibold text-foreground">
      {children}
    </span>
  )
}

function MetricRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right">{children}</span>
    </div>
  )
}

/** 可折叠分组：默认展开，标题行可点击切换。
 * 用 useState 自管开合，避免引入 base-ui Collapsible 依赖。 */
function CollapsibleSection({
  title,
  defaultOpen = true,
  children,
}: {
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="mt-4 border-t border-dashed pt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between rounded-sm py-0.5 text-left transition-colors hover:text-foreground"
      >
        <SectionTitle>{title}</SectionTitle>
        <ChevronDown
          className={cn(
            "size-4 text-muted-foreground transition-transform",
            !open && "-rotate-90",
          )}
        />
      </button>
      {open && <div className="mt-2.5">{children}</div>}
    </div>
  )
}

function ProcessingChip({ status, errorMessage }: { status: string; errorMessage: string | null }) {
  if (status === "pending") return <Badge variant="secondary">⏳ 待处理</Badge>
  if (status === "processing") return <Badge variant="warning">⏳ 处理中</Badge>
  if (status === "error") return <Badge variant="destructive" title={errorMessage ?? undefined}>⚠ 处理失败</Badge>
  return <Badge variant="success">✓ 已检索</Badge>
}

function ReviewChip({ reviewStatus }: { reviewStatus: string | null }) {
  if (!reviewStatus) return null
  if (reviewStatus === "pending") return <Badge variant="warning">待审核</Badge>
  if (reviewStatus === "approved") return <Badge variant="success">已通过</Badge>
  return <Badge variant="destructive">已驳回</Badge>
}

// ────────────────────────────────────────────────────────────────

/** Plan 41 — 条目编辑器 Dialog（左右双栏：左编辑器 / 右信息面板）。
 * 项目级规则：禁止点击空白 / ESC 关闭，仅显式按钮触发。 */
export function EntryEditorDialog({
  open,
  onOpenChange,
  kbId,
  entry,
  defaultFolderId,
  folders,
  embeddingConfigured,
  onSaved,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  kbId: string
  entry: KnowledgeEntry | null
  /** 新建条目时默认归属的文件夹（来自当前选中的文件树节点） */
  defaultFolderId?: string | null
  /** 文件夹列表（用于编辑时改文件夹） */
  folders: Folder[]
  /** #6 — KB 是否已配置 embedding；false 时禁用创建 / 内容变化的编辑 */
  embeddingConfigured: boolean
  onSaved: () => void
}) {
  const { theme } = useTheme()
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState("")
  const [folderId, setFolderId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // Spec 25 Plan B — 自动标签操作中
  const [autoTagBusy, setAutoTagBusy] = useState(false)

  const flatFolders = useMemo(() => flattenFolders(folders), [folders])
  const folderPath = useMemo(() => buildFolderPath(folders, folderId), [folders, folderId])

  useEffect(() => {
    if (open) {
      setTitle(entry?.title ?? "")
      setContent(entry?.content ?? "")
      setTags(entry?.tags ?? [])
      setTagInput("")
      setFolderId(entry ? entry.folder_id : (defaultFolderId ?? null))
    }
  }, [open, entry, defaultFolderId])

  function addTag(raw: string) {
    const t = raw.trim().replace(/,$/, "").trim()
    if (!t) return
    if (tags.includes(t)) {
      setTagInput("")
      return
    }
    setTags([...tags, t])
    setTagInput("")
  }

  function removeTag(t: string) {
    setTags(tags.filter((x) => x !== t))
  }

  // ── Spec 25 Plan B — auto_tags 接受 / 拒绝 / 重新生成 ────────
  async function handleAcceptAutoTag(tag: string) {
    if (!entry) return
    setAutoTagBusy(true)
    try {
      const updated = await entryApi.acceptAutoTag(kbId, entry.id, tag)
      // 本地状态同步：把 canonical 加进 user tags 输入区
      setTags(updated.tags ?? [])
      toast.success(`已接受：${tag}`)
      onSaved()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "接受失败")
    } finally {
      setAutoTagBusy(false)
    }
  }

  async function handleRejectAutoTag(tag: string) {
    if (!entry) return
    setAutoTagBusy(true)
    try {
      await entryApi.rejectAutoTag(kbId, entry.id, tag)
      toast.success(`已拒绝：${tag}`)
      onSaved()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "拒绝失败")
    } finally {
      setAutoTagBusy(false)
    }
  }

  async function handleRegenerateAutoTags() {
    if (!entry) return
    setAutoTagBusy(true)
    try {
      await entryApi.regenerateAutoTags(kbId, entry.id)
      toast.success("已排队重新生成；处理完成后刷新查看")
      // 不主动轮询 task；用户重新打开 / 刷新即可看到新结果
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "重新生成失败")
    } finally {
      setAutoTagBusy(false)
    }
  }

  async function handleSave() {
    if (!title.trim() || !content.trim()) {
      toast.error("标题和正文都是必填的")
      return
    }
    setSubmitting(true)
    try {
      if (entry) {
        await entryApi.update(kbId, entry.id, {
          title: title.trim(),
          content: content.trim(),
          tags: tags.length > 0 ? tags : undefined,
          folder_id: folderId,
        })
        toast.success(`已更新：${title.trim()}`)
      } else {
        await entryApi.create(kbId, {
          title: title.trim(),
          content: content.trim(),
          tags: tags.length > 0 ? tags : undefined,
          folder_id: folderId,
        })
        toast.success(`已创建：${title.trim()}`)
      }
      onSaved()
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSubmitting(false)
    }
  }

  const dark =
    theme === "dark" ||
    (theme === "system" && typeof window !== "undefined" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches)

  // 操作记录事件流（基于现有字段合成）
  const events = useMemo(() => {
    if (!entry) return []
    const list: { time: string; actor: string | null; action: string }[] = []
    list.push({ time: entry.created_at, actor: entry.created_by_name, action: "创建条目" })
    if (entry.updated_at && entry.updated_at !== entry.created_at) {
      list.push({ time: entry.updated_at, actor: entry.created_by_name, action: "编辑了内容" })
    }
    if (entry.reviewed_at) {
      const action =
        entry.review_status === "approved"
          ? "审核通过"
          : entry.review_status === "rejected"
            ? "审核驳回"
            : "审核操作"
      list.push({ time: entry.reviewed_at, actor: entry.reviewer_name, action })
    }
    return list.sort((a, b) => b.time.localeCompare(a.time))
  }, [entry])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="!max-w-[1200px] sm:!max-w-[1200px] flex h-[90vh] flex-col overflow-hidden p-0 gap-0"
      >
        <div className="flex shrink-0 items-center justify-between border-b px-5 py-3">
          <DialogTitle>{entry ? `编辑：${entry.title}` : "新建条目"}</DialogTitle>
        </div>

        {/* #6 — KB 缺 embedding 配置时顶部硬提示，禁用保存避免静默失败 */}
        {!embeddingConfigured && (
          <div className="shrink-0 border-b border-destructive/20 bg-destructive/5 px-5 py-2.5 text-sm">
            <span className="font-medium text-destructive">该知识库尚未配置 Embedding 模型。</span>
            <span className="ml-1 text-muted-foreground">
              {entry
                ? "可修改标题 / 标签 / 文件夹；如需修改正文，请先到「知识库配置 → Embedding」选择模型。"
                : "请先到「知识库配置 → Embedding」选择模型，再创建条目。"}
            </span>
          </div>
        )}

        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* ── 左侧：编辑器 ─────────────────────────────────────────── */}
          <div
            className="flex flex-1 flex-col gap-3 overflow-hidden px-5 py-4"
            data-color-mode={dark ? "dark" : "light"}
          >
            <div className="space-y-1.5">
              <Label htmlFor="entry-title">标题 *</Label>
              <Input
                id="entry-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                placeholder="条目标题（≤ 200 字）"
                autoFocus
              />
            </div>
            <div className="flex flex-1 min-h-0 flex-col space-y-1.5">
              <Label>正文 *</Label>
              <div className="flex-1 min-h-0 overflow-hidden rounded-md">
                <MDEditor
                  value={content}
                  onChange={(v) => setContent(v ?? "")}
                  height="100%"
                  preview="live"
                  style={{ height: "100%" }}
                />
              </div>
            </div>
          </div>

          {/* ── 右侧：信息面板 ────────────────────────────────────────── */}
          <aside className="w-[360px] shrink-0 overflow-y-auto border-l bg-muted/10 px-4 py-4">
            {/* 详情 — 直接展示，无卡片包装 */}
            <div>
              <SectionTitle>详情</SectionTitle>
              <div className="mt-2.5 space-y-2">
                <MetricRow label="状态">
                  {entry ? (
                    <ProcessingChip status={entry.status} errorMessage={entry.error_message} />
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </MetricRow>
                <MetricRow label="Token">
                  <span className="tabular-nums">
                    {entry ? entry.token_count.toLocaleString() : "—"}
                  </span>
                </MetricRow>
                <MetricRow label="创建">
                  {entry ? (
                    <>
                      <span className="text-foreground">{entry.created_by_name ?? "—"}</span>
                      <span className="text-muted-foreground"> · </span>
                      <TimeDisplay
                        value={entry.created_at}
                        className="text-muted-foreground"
                      />
                    </>
                  ) : (
                    <span className="text-muted-foreground">将在保存时记录</span>
                  )}
                </MetricRow>
                {entry && (
                  <MetricRow label="更新">
                    <TimeDisplay value={entry.updated_at} className="text-muted-foreground" />
                  </MetricRow>
                )}
                {entry?.review_status && (
                  <MetricRow label="审核">
                    <ReviewChip reviewStatus={entry.review_status} />
                  </MetricRow>
                )}
              </div>
              {entry?.status === "error" && entry.error_message && (
                <div className="mt-2.5 rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-1.5 text-sm text-destructive">
                  {entry.error_message}
                </div>
              )}
              {entry?.review_status === "rejected" && entry.review_comment && (
                <div className="mt-2.5 rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-1.5 text-sm">
                  <div className="font-medium text-destructive">驳回理由</div>
                  <div className="mt-0.5 whitespace-pre-wrap text-muted-foreground">
                    {entry.review_comment}
                  </div>
                </div>
              )}
            </div>

            {/* 标签 — 可折叠 */}
            <CollapsibleSection title="标签">
              <div
                className={cn(
                  "flex flex-wrap gap-1.5",
                  tags.length === 0 && "hidden",
                )}
              >
                {tags.map((t) => (
                  <Badge key={t} variant="secondary" className="gap-0.5 pr-0.5 text-xs">
                    <span>{t}</span>
                    <button
                      type="button"
                      onClick={() => removeTag(t)}
                      className="-mr-0.5 rounded-sm p-0.5 transition-colors hover:bg-foreground/10"
                      aria-label={`移除标签 ${t}`}
                    >
                      <X className="size-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              <Input
                className={cn("text-sm", tags.length > 0 && "mt-2")}
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === ",") {
                    e.preventDefault()
                    addTag(tagInput)
                  }
                  if (e.key === "Backspace" && !tagInput && tags.length > 0) {
                    e.preventDefault()
                    setTags(tags.slice(0, -1))
                  }
                }}
                onBlur={() => addTag(tagInput)}
                placeholder="输入后按 Enter / 逗号添加"
              />
            </CollapsibleSection>

            {/* 自动标签 — 可折叠（Spec 25 Plan B；仅编辑模式 + auto_tags 非空时显示） */}
            {entry && entry.auto_tags && entry.auto_tags.length > 0 && (
              <CollapsibleSection title="自动标签建议">
                <div className="flex flex-wrap gap-1.5">
                  {entry.auto_tags.map((at) => (
                    <Badge
                      key={at.tag}
                      variant="outline"
                      className="gap-0.5 pr-0.5 text-xs"
                      title={`${at.source} · 置信度 ${at.confidence.toFixed(2)}`}
                    >
                      <span>{at.tag}</span>
                      <span className="text-[9px] text-muted-foreground">
                        {(at.confidence * 100).toFixed(0)}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleAcceptAutoTag(at.tag)}
                        className="ml-0.5 rounded-sm p-0.5 text-success transition-colors hover:bg-success/10"
                        aria-label={`接受 ${at.tag}`}
                        title="接受为用户标签"
                      >
                        <Check className="size-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRejectAutoTag(at.tag)}
                        className="-mr-0.5 rounded-sm p-0.5 text-destructive transition-colors hover:bg-destructive/10"
                        aria-label={`拒绝 ${at.tag}`}
                        title="拒绝（加入黑名单）"
                      >
                        <X className="size-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
                <div className="mt-2 flex justify-end gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={handleRegenerateAutoTags}
                    disabled={autoTagBusy}
                  >
                    {autoTagBusy ? "排队中…" : "重新生成"}
                  </Button>
                </div>
              </CollapsibleSection>
            )}

            {/* 文件夹 — 可折叠 */}
            <CollapsibleSection title="文件夹">
              <div className="flex items-center gap-1 text-sm text-muted-foreground">
                {folderPath.length === 0 ? (
                  <span className="text-foreground">/ 根目录</span>
                ) : (
                  <>
                    <span>/</span>
                    {folderPath.map((p, i) => (
                      <span key={i} className="flex items-center gap-1">
                        <span className="text-foreground">{p}</span>
                        {i < folderPath.length - 1 && <ChevronRight className="size-3.5" />}
                      </span>
                    ))}
                  </>
                )}
              </div>
              <Select
                value={folderId ?? ROOT_FOLDER_VALUE}
                onValueChange={(v) => setFolderId(v === ROOT_FOLDER_VALUE ? null : v)}
              >
                <SelectTrigger className="mt-2 w-full text-sm">
                  <SelectValue placeholder="根目录" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ROOT_FOLDER_VALUE}>根目录</SelectItem>
                  {flatFolders.map((f) => (
                    <SelectItem key={f.id} value={f.id}>{f.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </CollapsibleSection>

            {/* 操作记录 — 可折叠（新建时隐藏整段） */}
            {entry && events.length > 0 && (
              <CollapsibleSection title="操作记录">
                <ol className="space-y-2 text-sm">
                  {events.map((ev, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                      <div className="flex-1 min-w-0">
                        <TimeDisplay
                          value={ev.time}
                          className="text-muted-foreground"
                        />
                        <span className="text-muted-foreground"> · </span>
                        <span className="text-foreground">{ev.actor ?? "—"}</span>
                        <span className="text-muted-foreground"> · </span>
                        <span>{ev.action}</span>
                      </div>
                    </li>
                  ))}
                </ol>
              </CollapsibleSection>
            )}
          </aside>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-2 rounded-b-xl border-t bg-muted/50 px-5 py-3">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          {(() => {
            // #6 — content 变化才会触发后端 rechunk + embed；未配置 embedding 时
            // 仅当新建条目 / 编辑改正文 才禁用保存。仅改 title/tags/folder 仍可保存。
            const contentChanged = content !== (entry?.content ?? "")
            const blockedByEmbedding = !embeddingConfigured && (!entry || contentChanged)
            return (
              <Button
                onClick={handleSave}
                disabled={
                  submitting || !title.trim() || !content.trim() || blockedByEmbedding
                }
                title={blockedByEmbedding ? "请先配置 Embedding 模型" : undefined}
              >
                {submitting ? "保存中..." : "保存"}
              </Button>
            )
          })()}
        </div>
      </DialogContent>
    </Dialog>
  )
}
