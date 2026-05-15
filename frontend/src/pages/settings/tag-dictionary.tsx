import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import {
  Edit2, FileClock, GitMerge, Plus, RefreshCw, Trash2,
} from "lucide-react"

import {
  Empty, Modal, Pagination, Select as SemiSelect, SideSheet, Table, Tag,
} from "@douyinfe/semi-ui"
import type { ColumnProps } from "@douyinfe/semi-ui/lib/es/table"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { TimeDisplay } from "@/components/shared/time-display"
import { knowledgeApi, type KnowledgeBase } from "@/api/knowledge"
import {
  tagDictionaryApi,
  type TagDictItem,
  type TagDictAuditItem,
} from "@/api/tag_dictionary"

const PAGE_SIZE = 50

/** Spec 25 §6 — 标签字典治理页。Apple "咨询台/utility card" 风格：
 * - hero strip：当前 KB + 三个核心 metric
 * - 工具行：搜索 + 过滤 + 主操作 CTA
 * - Semi Table：列表 + multi-select
 * - Semi Modal/SideSheet：所有弹层（替代 shadcn Dialog/Sheet 修朝上遮挡 + 一致性）
 */
export default function TagDictionaryPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [kbId, setKbId] = useState<string>("")
  const [items, setItems] = useState<TagDictItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [includeDeprecated, setIncludeDeprecated] = useState(false)
  const [loading, setLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  // 对话框状态
  const [createOpen, setCreateOpen] = useState(false)
  const [renameTarget, setRenameTarget] = useState<TagDictItem | null>(null)
  const [aliasesTarget, setAliasesTarget] = useState<TagDictItem | null>(null)
  const [mergeOpen, setMergeOpen] = useState(false)
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
    setSelectedIds([])
  }, [fetchDict])

  // ── hero strip 数据指标 ──────────────────────────────────────
  // 注意：metrics 反映"当前过滤集合"而非全 KB；当前 API 没有单独 stats endpoint，
  // 用本页 items 推断启用/已废弃数量。total 是过滤后总数。
  const metrics = useMemo(() => {
    const aliasesCount = items.reduce((s, i) => s + i.aliases.length, 0)
    const deprecatedCount = items.filter((i) => i.is_deprecated).length
    return { canonicals: total, aliases: aliasesCount, deprecated: deprecatedCount }
  }, [items, total])

  const currentKb = useMemo(() => kbs.find((k) => k.id === kbId), [kbs, kbId])

  const handleCreated = () => { setCreateOpen(false); fetchDict() }
  const handleRenamed = () => { setRenameTarget(null); fetchDict() }
  const handleAliasesSaved = () => { setAliasesTarget(null); fetchDict() }
  const handleMerged = () => { setMergeOpen(false); setSelectedIds([]); fetchDict() }

  // ── Semi Table columns ──────────────────────────────────────
  const columns: ColumnProps<TagDictItem>[] = [
    {
      title: "Canonical",
      dataIndex: "canonical",
      render: (text: string, record: TagDictItem) => (
        <span className={record.is_deprecated ? "opacity-60 font-medium" : "font-medium"}>
          {text}
        </span>
      ),
    },
    {
      title: "Aliases",
      dataIndex: "aliases",
      render: (aliases: string[]) =>
        aliases.length === 0 ? (
          <span className="text-xs text-muted-foreground">—</span>
        ) : (
          <div className="flex flex-wrap gap-1">
            {aliases.map((a) => (
              <Tag key={a} size="small" color="grey">{a}</Tag>
            ))}
          </div>
        ),
    },
    {
      title: "使用",
      dataIndex: "usage_count",
      align: "right",
      width: 80,
      render: (n: number) => <span className="tabular-nums">{n}</span>,
    },
    {
      title: "状态",
      dataIndex: "is_deprecated",
      width: 90,
      render: (d: boolean) =>
        d ? (
          <Tag color="grey" size="small">已废弃</Tag>
        ) : (
          <Tag color="green" size="small">启用</Tag>
        ),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 140,
      render: (v: string) => (
        <span className="text-xs text-muted-foreground">
          <TimeDisplay value={v} />
        </span>
      ),
    },
    {
      title: "",
      dataIndex: "_actions",
      width: 130,
      render: (_: unknown, record: TagDictItem) => (
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost" size="icon" className="size-7" title="改名"
            onClick={() => setRenameTarget(record)}
          >
            <Edit2 className="size-3.5" />
          </Button>
          <Button
            variant="ghost" size="icon" className="size-7" title="编辑别名"
            onClick={() => setAliasesTarget(record)}
          >
            <span className="text-xs font-mono">+</span>
          </Button>
          {!record.is_deprecated && (
            <Button
              variant="ghost" size="icon" className="size-7" title="废弃"
              onClick={() => handleSoftDelete(record)}
            >
              <Trash2 className="size-3.5 text-destructive" />
            </Button>
          )}
        </div>
      ),
    },
  ]

  // 废弃改用 Semi Modal.warning（替代 type: 'warning' 旧 API），自带图标 + danger 主按钮
  function handleSoftDelete(item: TagDictItem) {
    Modal.warning({
      title: `废弃 ${item.canonical}`,
      content:
        "软删除：is_deprecated=true，下次提取/写入不再命中此 canonical，" +
        "历史 entries/chunks 中的 tag 保留。可在「含已废弃」过滤后恢复。",
      okText: "废弃",
      cancelText: "取消",
      okButtonProps: { type: "danger" },
      onOk: async () => {
        try {
          await tagDictionaryApi.softDelete(kbId, item.id)
          toast.success("已废弃")
          fetchDict()
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "操作失败")
        }
      },
    })
  }

  return (
    <div className="space-y-6">
      {/* ── Global header ─────────────────────────────────────── */}
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

      {/* ── Hero strip (Apple parchment 风) ───────────────────── */}
      <section className="rounded-lg border bg-secondary/60 px-6 py-5">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="text-xs uppercase tracking-wide text-muted-foreground">
              当前知识库
            </span>
            {/* Semi Select：portal + z-index 1050，朝上不会被遮挡 */}
            <SemiSelect
              value={kbId || undefined}
              onChange={(v) => { setKbId(typeof v === "string" ? v : ""); setPage(1) }}
              placeholder="选择知识库"
              className="w-64"
              optionList={kbs.map((kb) => ({
                value: kb.id,
                label: `${kb.name}  (${kb.source_type})`,
              }))}
            />
            {currentKb && (
              <span className="text-xs text-muted-foreground">
                {currentKb.description?.slice(0, 60) ?? ""}
              </span>
            )}
          </div>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-6 border-t border-border/60 pt-4">
          <Metric label="Canonicals (过滤后)" value={metrics.canonicals} />
          <Metric label="本页 aliases 总数" value={metrics.aliases} />
          <Metric label="本页已废弃" value={metrics.deprecated} />
        </div>
      </section>

      {/* ── 工具行 ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="w-72"
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
          {selectedIds.length >= 2 && (
            <Button variant="outline" size="sm" onClick={() => setMergeOpen(true)}>
              <GitMerge className="size-4" />
              <span className="ml-1">合并 {selectedIds.length} 项</span>
            </Button>
          )}
          <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!kbId}>
            <Plus className="size-4" />
            <span className="ml-1">新建</span>
          </Button>
        </div>
      </div>

      {/* ── 主表格 (Semi Table) ───────────────────────────────── */}
      <Table
        columns={columns}
        dataSource={items}
        rowKey="id"
        size="small"
        loading={loading}
        pagination={false}
        empty={
          <div className="py-8">
            <Empty
              title={kbId ? "暂无字典条目" : "请先选择知识库"}
              description={
                kbId
                  ? "可点击右上角「新建」手动添加 canonical；或在条目里加 user tag 自动建。"
                  : ""
              }
            />
          </div>
        }
        rowSelection={{
          selectedRowKeys: selectedIds,
          onChange: (keys) =>
            setSelectedIds((keys ?? []).map((k) => String(k))),
        }}
      />

      {/* ── 分页 ──────────────────────────────────────────────── */}
      {total > PAGE_SIZE && (
        <div className="flex justify-end">
          <Pagination
            total={total}
            pageSize={PAGE_SIZE}
            currentPage={page}
            onPageChange={setPage}
            showTotal
          />
        </div>
      )}

      {/* ── 弹层 ──────────────────────────────────────────────── */}
      <CreateModal open={createOpen} onOpenChange={setCreateOpen} kbId={kbId} onSaved={handleCreated} />
      <RenameModal target={renameTarget} onClose={() => setRenameTarget(null)} kbId={kbId} onSaved={handleRenamed} />
      <AliasesModal target={aliasesTarget} onClose={() => setAliasesTarget(null)} kbId={kbId} onSaved={handleAliasesSaved} />
      <MergeModal
        open={mergeOpen} onOpenChange={setMergeOpen} kbId={kbId}
        sources={items.filter((i) => selectedIds.includes(i.id))}
        onSaved={handleMerged}
      />
      <AuditSideSheet open={auditOpen} onOpenChange={setAuditOpen} kbId={kbId} />
    </div>
  )
}


// ─── 公共组件 ────────────────────────────────────────────────────


function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col">
      <span className="text-2xl font-semibold tabular-nums text-foreground">
        {value.toLocaleString()}
      </span>
      <span className="mt-0.5 text-xs text-muted-foreground">{label}</span>
    </div>
  )
}


// ─── 弹层组件（Semi Modal + SideSheet） ──────────────────────────


function CreateModal({
  open, onOpenChange, kbId, onSaved,
}: { open: boolean; onOpenChange: (v: boolean) => void; kbId: string; onSaved: () => void }) {
  const [canonical, setCanonical] = useState("")
  const [aliasesInput, setAliasesInput] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (open) { setCanonical(""); setAliasesInput("") } }, [open])

  async function handleSave() {
    if (!canonical.trim()) return
    setSaving(true)
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
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      visible={open}
      onCancel={() => onOpenChange(false)}
      onOk={handleSave}
      title="新建字典条目"
      okText="保存"
      cancelText="取消"
      okButtonProps={{ disabled: !canonical.trim() || saving }}
      maskClosable={false}
      keepDOM={false}
    >
      <div className="space-y-3">
        <div className="space-y-1.5">
          <label className="text-sm">Canonical *</label>
          <Input
            value={canonical} onChange={(e) => setCanonical(e.target.value)}
            placeholder="规范名（如：退款）" maxLength={64}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm">Aliases</label>
          <Input
            value={aliasesInput} onChange={(e) => setAliasesInput(e.target.value)}
            placeholder="逗号分隔（如：退单, 退货）"
          />
        </div>
      </div>
    </Modal>
  )
}


function RenameModal({
  target, onClose, kbId, onSaved,
}: { target: TagDictItem | null; onClose: () => void; kbId: string; onSaved: () => void }) {
  const [next, setNext] = useState("")
  const [saving, setSaving] = useState(false)
  useEffect(() => { if (target) setNext(target.canonical) }, [target])

  async function handleSave() {
    if (!target) return
    setSaving(true)
    try {
      await tagDictionaryApi.rename(kbId, target.id, next.trim())
      toast.success("已改名，回填异步进行")
      onSaved()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "改名失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      visible={!!target}
      onCancel={onClose}
      onOk={handleSave}
      title={`改名：${target?.canonical ?? ""}`}
      okText="确认改名"
      cancelText="取消"
      okButtonProps={{
        disabled: !next.trim() || next === target?.canonical || saving,
      }}
      maskClosable={false}
      keepDOM={false}
    >
      <p className="text-xs text-muted-foreground">
        旧 canonical 会自动进入 aliases；触发异步回填所有 entries.tags 和 chunks.chunk_tags 改写。
      </p>
      <Input value={next} onChange={(e) => setNext(e.target.value)} maxLength={64} className="mt-3" />
    </Modal>
  )
}


function AliasesModal({
  target, onClose, kbId, onSaved,
}: { target: TagDictItem | null; onClose: () => void; kbId: string; onSaved: () => void }) {
  const [aliases, setAliases] = useState<string[]>([])
  const [input, setInput] = useState("")
  const [saving, setSaving] = useState(false)
  useEffect(() => { if (target) { setAliases([...target.aliases]); setInput("") } }, [target])

  function addAlias(raw: string) {
    const v = raw.trim()
    if (!v || aliases.includes(v)) { setInput(""); return }
    setAliases([...aliases, v]); setInput("")
  }

  async function handleSave() {
    if (!target) return
    setSaving(true)
    try {
      await tagDictionaryApi.setAliases(kbId, target.id, aliases)
      toast.success("已保存")
      onSaved()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      visible={!!target}
      onCancel={onClose}
      onOk={handleSave}
      title={`编辑别名：${target?.canonical ?? ""}`}
      okText="保存"
      cancelText="取消"
      okButtonProps={{ disabled: saving }}
      maskClosable={false}
      keepDOM={false}
    >
      <div className="flex flex-wrap gap-1.5">
        {aliases.map((a) => (
          <Tag
            key={a}
            color="grey"
            closable
            onClose={() => setAliases(aliases.filter((x) => x !== a))}
          >
            {a}
          </Tag>
        ))}
        {aliases.length === 0 && (
          <span className="text-xs text-muted-foreground">暂无 alias</span>
        )}
      </div>
      <Input
        className="mt-3"
        placeholder="输入后按 Enter / 逗号添加"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addAlias(input) }
        }}
        onBlur={() => addAlias(input)}
      />
    </Modal>
  )
}


function MergeModal({
  open, onOpenChange, kbId, sources, onSaved,
}: {
  open: boolean; onOpenChange: (v: boolean) => void;
  kbId: string; sources: TagDictItem[]; onSaved: () => void
}) {
  const [targetId, setTargetId] = useState<string>("")
  const [saving, setSaving] = useState(false)

  const candidates = useMemo(() => sources, [sources])
  useEffect(() => {
    if (open && candidates.length > 0) setTargetId(candidates[0].id)
  }, [open, candidates])

  async function handleMerge() {
    const source_ids = sources.map((s) => s.id).filter((id) => id !== targetId)
    if (source_ids.length === 0) return
    setSaving(true)
    try {
      await tagDictionaryApi.merge(kbId, { source_ids, target_id: targetId })
      toast.success("已合并，回填异步进行")
      onSaved()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "合并失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      visible={open}
      onCancel={() => onOpenChange(false)}
      onOk={handleMerge}
      title={`合并 ${sources.length} 个字典条目`}
      okText="确认合并"
      cancelText="取消"
      okButtonProps={{
        type: "danger",
        disabled: !targetId || sources.length < 2 || saving,
      }}
      maskClosable={false}
      keepDOM={false}
    >
      <p className="text-xs text-muted-foreground">
        选择目标 canonical，其余条目的 canonical+aliases 全部并入 target.aliases，源条目软删除。
        触发异步回填所有 entries.tags / chunks.chunk_tags 改写。
      </p>
      <div className="mt-3 space-y-1">
        {sources.map((s) => (
          <label
            key={s.id}
            className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted/30"
          >
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
    </Modal>
  )
}


function AuditSideSheet({
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
    <SideSheet
      visible={open}
      onCancel={() => onOpenChange(false)}
      title="操作历史"
      placement="right"
      width={640}
      maskClosable={false}
    >
      <div className="space-y-2">
        {loading ? (
          <p className="text-center text-sm text-muted-foreground">加载中…</p>
        ) : items.length === 0 ? (
          <Empty title="暂无记录" description="字典操作（创建/改名/合并/废弃/别名变更）发生后会在此留痕。" />
        ) : items.map((it) => (
          <div key={it.id} className="rounded-md border p-3 text-xs">
            <div className="flex items-center justify-between">
              <Tag color="blue" size="small">{it.op}</Tag>
              <span className="text-muted-foreground">
                <TimeDisplay value={it.created_at} />
              </span>
            </div>
            {it.affected_entries !== null && (
              <div className="mt-1 text-muted-foreground">
                影响 {it.affected_entries} 条 entries
              </div>
            )}
            <details className="mt-1.5 text-muted-foreground">
              <summary className="cursor-pointer hover:text-foreground">详情</summary>
              <pre className="mt-1 overflow-x-auto rounded bg-muted/30 p-2 text-[10px]">
                before: {JSON.stringify(it.before, null, 2)}
                {"\n\n"}
                after:  {JSON.stringify(it.after, null, 2)}
              </pre>
            </details>
          </div>
        ))}
      </div>
    </SideSheet>
  )
}

