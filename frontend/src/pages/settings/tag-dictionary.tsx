import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import {
  ChevronLeft, ChevronRight, Edit2, FileClock, GitMerge, Plus,
  RefreshCw, Trash2, X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "@/components/ui/sheet"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { TimeDisplay } from "@/components/shared/time-display"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { knowledgeApi, type KnowledgeBase } from "@/api/knowledge"
import {
  tagDictionaryApi,
  type TagDictItem,
  type TagDictAuditItem,
} from "@/api/tag_dictionary"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 50

export default function TagDictionaryPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [kbId, setKbId] = useState<string>("")
  const [items, setItems] = useState<TagDictItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [includeDeprecated, setIncludeDeprecated] = useState(false)
  const [loading, setLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // 对话框状态
  const [createOpen, setCreateOpen] = useState(false)
  const [renameTarget, setRenameTarget] = useState<TagDictItem | null>(null)
  const [aliasesTarget, setAliasesTarget] = useState<TagDictItem | null>(null)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<TagDictItem | null>(null)
  const [auditOpen, setAuditOpen] = useState(false)

  // ── 加载 KB 列表 ──────────────────────────────────────────────
  useEffect(() => {
    knowledgeApi.listKBs({ page_size: "200" }).then((r) => {
      setKbs(r.items)
      if (r.items.length > 0) {
        setKbId((prev) => prev || r.items[0].id)
      }
    }).catch(() => {})
  }, [])

  // ── 加载当前 KB 字典 ─────────────────────────────────────────
  const fetchDict = useCallback(async () => {
    if (!kbId) return
    setLoading(true)
    try {
      const res = await tagDictionaryApi.list(kbId, {
        page, page_size: PAGE_SIZE,
        search: search.trim() || undefined,
        include_deprecated: includeDeprecated,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [kbId, page, search, includeDeprecated])

  useEffect(() => {
    fetchDict()
    setSelectedIds(new Set())
  }, [fetchDict])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const allCheckedOnPage = items.length > 0 && items.every((i) => selectedIds.has(i.id))

  const toggleSelectAll = (checked: boolean) => {
    const next = new Set(selectedIds)
    if (checked) items.forEach((i) => next.add(i.id))
    else items.forEach((i) => next.delete(i.id))
    setSelectedIds(next)
  }

  const handleCreated = () => { setCreateOpen(false); fetchDict() }
  const handleRenamed = () => { setRenameTarget(null); fetchDict() }
  const handleAliasesSaved = () => { setAliasesTarget(null); fetchDict() }
  const handleMerged = () => { setMergeOpen(false); setSelectedIds(new Set()); fetchDict() }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">标签字典</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            KB 内 canonical 与 aliases 治理；合并/改名触发异步回填 entries.tags 与 chunks.chunk_tags
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setAuditOpen(true)}>
            <FileClock className="size-4" />
            <span className="ml-1">操作历史</span>
          </Button>
          <Button variant="outline" size="sm" onClick={fetchDict} disabled={loading}>
            <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} />
            <span className="ml-1">刷新</span>
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={kbId} onValueChange={(v) => { setKbId(v ?? ""); setPage(1) }}>
          <SelectTrigger className="w-64">
            <SelectValue placeholder="选择知识库" />
          </SelectTrigger>
          <SelectContent>
            {kbs.map((kb) => (
              <SelectItem key={kb.id} value={kb.id}>
                {kb.name}
                <span className="ml-2 text-xs text-muted-foreground">
                  ({kb.source_type})
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className="w-56"
          placeholder="搜索 canonical / alias..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
        />
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Checkbox
            checked={includeDeprecated}
            onCheckedChange={(v) => { setIncludeDeprecated(!!v); setPage(1) }}
          />
          含已废弃
        </label>
        <div className="ml-auto flex items-center gap-2">
          {selectedIds.size >= 2 && (
            <Button variant="outline" size="sm" onClick={() => setMergeOpen(true)}>
              <GitMerge className="size-4" />
              <span className="ml-1">合并 {selectedIds.size} 项</span>
            </Button>
          )}
          <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!kbId}>
            <Plus className="size-4" />
            <span className="ml-1">新建</span>
          </Button>
        </div>
      </div>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 w-8">
                <Checkbox
                  checked={allCheckedOnPage}
                  onCheckedChange={(v) => toggleSelectAll(!!v)}
                />
              </th>
              <th className="px-3 py-2">Canonical</th>
              <th className="px-3 py-2">Aliases</th>
              <th className="px-3 py-2 text-right w-20">使用</th>
              <th className="px-3 py-2 w-20">状态</th>
              <th className="px-3 py-2 w-32">更新时间</th>
              <th className="px-3 py-2 w-1" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">加载中...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                {kbId ? "该 KB 暂无字典条目" : "请先选择知识库"}
              </td></tr>
            ) : (
              items.map((it) => (
                <tr key={it.id} className={cn(
                  "border-b last:border-0",
                  it.is_deprecated && "opacity-60",
                )}>
                  <td className="px-3 py-2">
                    <Checkbox
                      checked={selectedIds.has(it.id)}
                      onCheckedChange={(v) => {
                        const next = new Set(selectedIds)
                        if (v) next.add(it.id); else next.delete(it.id)
                        setSelectedIds(next)
                      }}
                    />
                  </td>
                  <td className="px-3 py-2 font-medium">{it.canonical}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {it.aliases.length === 0 ? (
                        <span className="text-xs text-muted-foreground">—</span>
                      ) : it.aliases.map((a) => (
                        <Badge key={a} variant="outline" className="text-[10px]">{a}</Badge>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{it.usage_count}</td>
                  <td className="px-3 py-2">
                    {it.is_deprecated
                      ? <Badge variant="secondary">已废弃</Badge>
                      : <Badge variant="success">启用</Badge>}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    <TimeDisplay value={it.updated_at} />
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="icon" className="size-7"
                              title="改名"
                              onClick={() => setRenameTarget(it)}>
                        <Edit2 className="size-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="size-7"
                              title="编辑别名"
                              onClick={() => setAliasesTarget(it)}>
                        <span className="text-xs font-mono">{"+"}</span>
                      </Button>
                      {!it.is_deprecated && (
                        <Button variant="ghost" size="icon" className="size-7"
                                title="废弃"
                                onClick={() => setDeleteTarget(it)}>
                          <Trash2 className="size-3.5 text-destructive" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-end gap-2">
        <span className="text-xs text-muted-foreground tabular-nums">
          {page} / {totalPages} (共 {total} 条)
        </span>
        <Button variant="outline" size="icon" className="size-8" disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}>
          <ChevronLeft className="size-4" />
        </Button>
        <Button variant="outline" size="icon" className="size-8" disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
          <ChevronRight className="size-4" />
        </Button>
      </div>

      {/* 子 Dialog */}
      <CreateDialog open={createOpen} onOpenChange={setCreateOpen} kbId={kbId} onSaved={handleCreated} />
      <RenameDialog target={renameTarget} onOpenChange={() => setRenameTarget(null)}
                    kbId={kbId} onSaved={handleRenamed} />
      <AliasesDialog target={aliasesTarget} onOpenChange={() => setAliasesTarget(null)}
                     kbId={kbId} onSaved={handleAliasesSaved} />
      <MergeDialog open={mergeOpen} onOpenChange={setMergeOpen} kbId={kbId}
                   sources={items.filter((i) => selectedIds.has(i.id))}
                   onSaved={handleMerged} />
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title={`废弃 ${deleteTarget?.canonical ?? ""}`}
        description="软删除：is_deprecated=true，下次提取/写入不再命中此 canonical，历史 entries/chunks 中的 tag 保留。可在「含已废弃」过滤后恢复。"
        confirmText="废弃"
        destructive
        onConfirm={async () => {
          if (!deleteTarget) return
          try {
            await tagDictionaryApi.softDelete(kbId, deleteTarget.id)
            toast.success("已废弃")
            fetchDict()
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "操作失败")
          }
        }}
      />
      <AuditSheet open={auditOpen} onOpenChange={setAuditOpen} kbId={kbId} />
    </div>
  )
}


// ─── 子组件 ──────────────────────────────────────────────────────


function CreateDialog({
  open, onOpenChange, kbId, onSaved,
}: { open: boolean; onOpenChange: (v: boolean) => void; kbId: string; onSaved: () => void }) {
  const [canonical, setCanonical] = useState("")
  const [aliasesInput, setAliasesInput] = useState("")

  useEffect(() => { if (open) { setCanonical(""); setAliasesInput("") } }, [open])

  async function handleSave() {
    if (!canonical.trim()) return
    try {
      const aliases = aliasesInput.split(/[,，]/).map((a) => a.trim()).filter(Boolean)
      await tagDictionaryApi.create(kbId, {
        canonical: canonical.trim(),
        aliases: aliases.length > 0 ? aliases : undefined,
      })
      toast.success("已创建")
      onSaved()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "创建失败")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>新建字典条目</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm">Canonical *</label>
            <Input value={canonical} onChange={(e) => setCanonical(e.target.value)}
                   placeholder="规范名（如：退款）" maxLength={64} />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm">Aliases</label>
            <Input value={aliasesInput} onChange={(e) => setAliasesInput(e.target.value)}
                   placeholder="逗号分隔（如：退单, 退货）" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSave} disabled={!canonical.trim()}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function RenameDialog({
  target, onOpenChange, kbId, onSaved,
}: { target: TagDictItem | null; onOpenChange: () => void; kbId: string; onSaved: () => void }) {
  const [next, setNext] = useState("")
  useEffect(() => { if (target) setNext(target.canonical) }, [target])

  return (
    <Dialog open={!!target} onOpenChange={(v) => !v && onOpenChange()}>
      <DialogContent>
        <DialogHeader><DialogTitle>改名：{target?.canonical}</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">
          旧 canonical 会自动进入 aliases；触发异步回填所有 entries.tags 和 chunks.chunk_tags 改写。
        </p>
        <Input value={next} onChange={(e) => setNext(e.target.value)} maxLength={64} className="mt-2" />
        <DialogFooter>
          <Button variant="outline" onClick={onOpenChange}>取消</Button>
          <Button
            disabled={!next.trim() || next === target?.canonical}
            onClick={async () => {
              if (!target) return
              try {
                await tagDictionaryApi.rename(kbId, target.id, next.trim())
                toast.success("已改名，回填异步进行")
                onSaved()
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "改名失败")
              }
            }}
          >确认改名</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function AliasesDialog({
  target, onOpenChange, kbId, onSaved,
}: { target: TagDictItem | null; onOpenChange: () => void; kbId: string; onSaved: () => void }) {
  const [aliases, setAliases] = useState<string[]>([])
  const [input, setInput] = useState("")
  useEffect(() => { if (target) { setAliases([...target.aliases]); setInput("") } }, [target])

  function addAlias(raw: string) {
    const v = raw.trim()
    if (!v || aliases.includes(v)) { setInput(""); return }
    setAliases([...aliases, v]); setInput("")
  }

  return (
    <Dialog open={!!target} onOpenChange={(v) => !v && onOpenChange()}>
      <DialogContent>
        <DialogHeader><DialogTitle>编辑别名：{target?.canonical}</DialogTitle></DialogHeader>
        <div className="flex flex-wrap gap-1.5">
          {aliases.map((a) => (
            <Badge key={a} variant="secondary" className="gap-0.5 pr-0.5">
              {a}
              <button onClick={() => setAliases(aliases.filter((x) => x !== a))}
                      className="rounded-sm p-0.5 hover:bg-foreground/10">
                <X className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
        <Input
          className="mt-2"
          placeholder="输入后按 Enter / 逗号添加"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addAlias(input) }
          }}
          onBlur={() => addAlias(input)}
        />
        <DialogFooter>
          <Button variant="outline" onClick={onOpenChange}>取消</Button>
          <Button onClick={async () => {
            if (!target) return
            try {
              await tagDictionaryApi.setAliases(kbId, target.id, aliases)
              toast.success("已保存")
              onSaved()
            } catch (e) {
              toast.error(e instanceof Error ? e.message : "保存失败")
            }
          }}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function MergeDialog({
  open, onOpenChange, kbId, sources, onSaved,
}: {
  open: boolean; onOpenChange: (v: boolean) => void;
  kbId: string; sources: TagDictItem[]; onSaved: () => void
}) {
  const [targetId, setTargetId] = useState<string>("")

  const candidates = useMemo(() => sources, [sources])
  useEffect(() => {
    if (open && candidates.length > 0) setTargetId(candidates[0].id)
  }, [open, candidates])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>合并 {sources.length} 个字典条目</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">
          选择目标 canonical，其余条目的 canonical+aliases 全部并入 target.aliases，源条目软删除。
          触发异步回填所有 entries.tags / chunks.chunk_tags 改写。
        </p>
        <div className="mt-2 space-y-1">
          {sources.map((s) => (
            <label key={s.id} className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm">
              <input
                type="radio"
                name="merge_target"
                checked={targetId === s.id}
                onChange={() => setTargetId(s.id)}
              />
              <span className="font-medium">{s.canonical}</span>
              <span className="text-xs text-muted-foreground">
                ({s.usage_count} 次使用 / {s.aliases.length} aliases)
              </span>
            </label>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button
            variant="destructive"
            disabled={!targetId || sources.length < 2}
            onClick={async () => {
              const source_ids = sources.map((s) => s.id).filter((id) => id !== targetId)
              if (source_ids.length === 0) return
              try {
                await tagDictionaryApi.merge(kbId, { source_ids, target_id: targetId })
                toast.success("已合并，回填异步进行")
                onSaved()
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "合并失败")
              }
            }}
          >确认合并</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function AuditSheet({
  open, onOpenChange, kbId,
}: { open: boolean; onOpenChange: (v: boolean) => void; kbId: string }) {
  const [items, setItems] = useState<TagDictAuditItem[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !kbId) return
    setLoading(true)
    tagDictionaryApi.listAudit(kbId)
      .then((r) => setItems(r.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [open, kbId])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[640px] sm:max-w-[640px]">
        <SheetHeader><SheetTitle>操作历史</SheetTitle></SheetHeader>
        <div className="mt-4 overflow-y-auto pr-2 space-y-2">
          {loading ? (
            <p className="text-center text-sm text-muted-foreground">加载中…</p>
          ) : items.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground">暂无记录</p>
          ) : items.map((it) => (
            <div key={it.id} className="rounded-md border p-2.5 text-xs space-y-1">
              <div className="flex items-center justify-between">
                <Badge variant="outline">{it.op}</Badge>
                <span className="text-muted-foreground">
                  <TimeDisplay value={it.created_at} />
                </span>
              </div>
              {it.affected_entries !== null && (
                <div className="text-muted-foreground">影响 {it.affected_entries} 条 entries</div>
              )}
              <details className="text-muted-foreground">
                <summary className="cursor-pointer hover:text-foreground">详情</summary>
                <pre className="mt-1 overflow-x-auto rounded bg-muted/30 p-1.5 text-[10px]">
                  before: {JSON.stringify(it.before, null, 2)}
                  {"\n\n"}
                  after:  {JSON.stringify(it.after, null, 2)}
                </pre>
              </details>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}
