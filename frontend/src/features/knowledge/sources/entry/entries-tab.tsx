import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Edit, Plus, Search, Trash2, Upload } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { TimeDisplay } from "@/components/shared/time-display"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { FileTree } from "@/features/knowledge/components/file-tree"
import { EntryEditorDialog } from "./entry-editor-dialog"
import { entryApi, type KnowledgeEntry } from "@/api/entry"
import { knowledgeApi, type Folder, type KnowledgeBase } from "@/api/knowledge"

/** Plan 41 — 条目型 KB 详情主区。二栏布局：文件树 + 条目表格。
 * 用户在大知识量场景能用文件夹分类组织条目。 */
export function EntriesTab({ kb }: { kb: KnowledgeBase }) {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([])
  const [folders, setFolders] = useState<Folder[]>([])
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<KnowledgeEntry | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeEntry | null>(null)
  const [importing, setImporting] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [batchAction, setBatchAction] = useState<"delete" | "archive" | null>(null)
  const importInputRef = useRef<HTMLInputElement>(null)

  // 客户端模糊过滤（标题 / 内容前 200 字 / tags）
  const filteredEntries = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return entries
    return entries.filter((e) => {
      if (e.title.toLowerCase().includes(q)) return true
      if (e.content.slice(0, 200).toLowerCase().includes(q)) return true
      if ((e.tags ?? []).some((t) => t.toLowerCase().includes(q))) return true
      return false
    })
  }, [entries, searchQuery])

  const reloadFolders = useCallback(async () => {
    try {
      const f = await knowledgeApi.listFolders(kb.id)
      setFolders(f)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "加载文件夹失败")
    }
  }, [kb.id])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await entryApi.list(kb.id, 1, 100, selectedFolderId)
      setEntries(r.items)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [kb.id, selectedFolderId])

  useEffect(() => { reloadFolders() }, [reloadFolders])

  useEffect(() => { load() }, [load])

  // 当存在 processing 状态条目时，10s 轮询直到全部完成
  useEffect(() => {
    if (!entries.some((e) => e.status === "processing" || e.status === "pending")) return
    const t = setInterval(load, 10_000)
    return () => clearInterval(t)
  }, [entries, load])

  function openCreate() {
    // 新建条目时默认放当前选中的文件夹
    setEditing(null)
    setEditorOpen(true)
  }

  // 当前选中文件夹的名字（顶部 breadcrumb 显示）
  function currentFolderName() {
    if (!selectedFolderId) return "全部条目"
    const find = (list: Folder[]): Folder | null => {
      for (const f of list) {
        if (f.id === selectedFolderId) return f
        const c = find(f.children ?? [])
        if (c) return c
      }
      return null
    }
    return find(folders)?.name ?? "全部条目"
  }

  function openEdit(entry: KnowledgeEntry) {
    setEditing(entry)
    setEditorOpen(true)
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await entryApi.delete(kb.id, deleteTarget.id)
      toast.success(`已删除：${deleteTarget.title}`)
      setDeleteTarget(null)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  function toggleSelect(id: string, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  function toggleSelectAll(checked: boolean) {
    if (checked) {
      setSelectedIds(new Set(filteredEntries.map((e) => e.id)))
    } else {
      setSelectedIds(new Set())
    }
  }

  async function handleBatchAction() {
    if (!batchAction || selectedIds.size === 0) return
    const ids = Array.from(selectedIds)
    try {
      if (batchAction === "delete") {
        await entryApi.batchDelete(kb.id, ids)
        toast.success(`已删除 ${ids.length} 条`)
      } else {
        await entryApi.batchArchive(kb.id, ids)
        toast.success(`已归档 ${ids.length} 条`)
      }
      setSelectedIds(new Set())
      setBatchAction(null)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "批量操作失败")
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.match(/\.(csv|jsonl|ndjson)$/i)) {
      toast.error("仅支持 .csv / .jsonl 格式")
      if (importInputRef.current) importInputRef.current.value = ""
      return
    }
    setImporting(true)
    try {
      await entryApi.importBatch(kb.id, file)
      toast.success("导入任务已提交，后台处理中...")
      // 5s 后自动刷新列表（async task 期间陆续可见）
      setTimeout(load, 5000)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "导入失败")
    } finally {
      setImporting(false)
      if (importInputRef.current) importInputRef.current.value = ""
    }
  }

  return (
    <div className="flex h-full min-h-0 gap-3">
      {/* 左栏：文件树（与文件型 documents tab 同 220px 宽度） */}
      <aside className="h-full w-56 shrink-0 overflow-y-auto rounded-lg border bg-card p-2">
        <FileTree
          kbId={kb.id}
          folders={folders}
          selectedFolderId={selectedFolderId}
          onSelectFolder={(fid) => setSelectedFolderId(fid)}
          onFoldersChanged={reloadFolders}
        />
      </aside>

      {/* 右栏：条目表格 */}
      <div className="flex h-full min-w-0 flex-1 flex-col space-y-3 overflow-y-auto">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{currentFolderName()}</span>
          <span className="text-xs text-muted-foreground">
            {loading
              ? "加载中…"
              : searchQuery.trim()
                ? `· ${filteredEntries.length} / ${entries.length}`
                : `· ${entries.length} 条`}
          </span>
        </div>
        {/* 搜索框 */}
        <div className="relative max-w-xs flex-1">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索标题 / 内容 / 标签..."
            className="h-8 pl-7 text-xs"
          />
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={importInputRef}
            type="file"
            accept=".csv,.jsonl,.ndjson"
            className="hidden"
            onChange={handleImport}
          />
          <Button
            variant="outline"
            disabled={importing}
            onClick={() => importInputRef.current?.click()}
          >
            <Upload className="mr-1 size-4" />
            {importing ? "提交中..." : "批量导入"}
          </Button>
          <Button onClick={openCreate}>
            <Plus className="mr-1 size-4" /> 新建条目
          </Button>
        </div>
      </div>

      {/* 批量操作栏：选中后显示 */}
      {selectedIds.size > 0 && (
        <div className="flex items-center justify-between rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
          <span className="text-primary">已选 {selectedIds.size} 条</span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setBatchAction("archive")}
            >
              批量归档
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() => setBatchAction("delete")}
            >
              批量删除
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedIds(new Set())}
            >
              取消
            </Button>
          </div>
        </div>
      )}

      {!loading && filteredEntries.length === 0 ? (
        <div className="rounded-md border py-12 text-center text-sm text-muted-foreground">
          尚未创建任何条目。点击「新建条目」开始添加 FAQ / SOP / 词条。
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-left text-xs font-medium text-muted-foreground">
                <th className="px-3 py-2 w-8">
                  <Checkbox
                    checked={
                      filteredEntries.length > 0 &&
                      filteredEntries.every((e) => selectedIds.has(e.id))
                    }
                    onCheckedChange={(v) => toggleSelectAll(!!v)}
                  />
                </th>
                <th className="px-3 py-2">标题</th>
                <th className="px-3 py-2">标签</th>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2 text-right">Token</th>
                <th className="px-3 py-2 text-right">更新时间</th>
                <th className="px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredEntries.map((e) => (
                <tr
                  key={e.id}
                  className="border-b last:border-b-0 cursor-pointer hover:bg-muted/30"
                  onClick={() => openEdit(e)}
                >
                  <td className="px-3 py-2" onClick={(ev) => ev.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(e.id)}
                      onCheckedChange={(v) => toggleSelect(e.id, !!v)}
                    />
                  </td>
                  <td className="px-3 py-2 font-medium">{e.title}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {(e.tags ?? []).slice(0, 3).map((t, i) => (
                        <Badge key={i} variant="outline" className="text-[10px]">
                          {t}
                        </Badge>
                      ))}
                      {(e.tags?.length ?? 0) > 3 && (
                        <span className="text-[10px] text-muted-foreground">
                          +{(e.tags?.length ?? 0) - 3}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-0.5">
                      {/* 处理状态（pending/processing/error 才显示，completed 时让位审核状态） */}
                      {e.status === "processing" && (
                        <span className="text-xs text-warning">⏳ 处理中</span>
                      )}
                      {e.status === "pending" && (
                        <span className="text-xs text-muted-foreground">⏳ 待处理</span>
                      )}
                      {e.status === "error" && (
                        <span
                          className="text-xs text-destructive"
                          title={e.error_message ?? undefined}
                        >
                          ⚠ 处理失败
                        </span>
                      )}
                      {/* 审核状态（仅 review_required KB 才有值） */}
                      {e.status === "completed" && e.review_status === "pending" && (
                        <span className="text-xs text-warning">待审</span>
                      )}
                      {e.status === "completed" && e.review_status === "approved" && (
                        <span className="text-xs text-success">已通过</span>
                      )}
                      {e.status === "completed" && e.review_status === "rejected" && (
                        <span className="text-xs text-destructive">已驳回</span>
                      )}
                      {e.status === "completed" && e.review_status === null && (
                        <span className="text-xs text-success">就绪</span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {e.token_count}
                  </td>
                  <td className="px-3 py-2 text-right text-xs text-muted-foreground">
                    <TimeDisplay value={e.updated_at} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7"
                        onClick={(ev) => {
                          ev.stopPropagation()
                          openEdit(e)
                        }}
                        title="编辑"
                      >
                        <Edit className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 text-destructive hover:text-destructive"
                        onClick={(ev) => {
                          ev.stopPropagation()
                          setDeleteTarget(e)
                        }}
                        title="删除"
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      </div>{/* 右栏 end */}

      <EntryEditorDialog
        open={editorOpen}
        onOpenChange={setEditorOpen}
        kbId={kb.id}
        entry={editing}
        defaultFolderId={selectedFolderId}
        folders={folders}
        onSaved={load}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title={`删除条目「${deleteTarget?.title ?? ""}」`}
        description="此操作将永久删除该条目及其所有切片，无法恢复。"
        confirmText="永久删除"
        destructive
        onConfirm={handleDelete}
      />

      <ConfirmDialog
        open={batchAction !== null}
        onOpenChange={(v) => { if (!v) setBatchAction(null) }}
        title={
          batchAction === "delete"
            ? `批量删除 ${selectedIds.size} 条条目`
            : `批量归档 ${selectedIds.size} 条条目`
        }
        description={
          batchAction === "delete"
            ? "此操作将永久删除所选条目及其所有切片，无法恢复。"
            : "归档的条目从列表和检索路径过滤，不会丢失数据。"
        }
        confirmText={batchAction === "delete" ? "永久删除" : "确认归档"}
        destructive={batchAction === "delete"}
        onConfirm={handleBatchAction}
      />
    </div>
  )
}
