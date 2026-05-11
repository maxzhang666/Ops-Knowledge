import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Plus, Trash2, PlayCircle, CheckCircle2, XCircle, Loader2,
  Save, Pencil, Search, Check, ChevronDown,
} from "lucide-react"
import { toast } from "sonner"
import {
  Button, Card, Tag, Modal, Input, Select, Switch, Tabs, TabPane,
  Dropdown, Table, Spin,
} from "@douyinfe/semi-ui"
import type { ColumnProps } from "@douyinfe/semi-ui/lib/es/table"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { modelApi, type ModelProvider, type ProviderTypeSchema, type RegistryEntry } from "@/api/model"
import { systemApi } from "@/api/system"

const TYPE_TAG: Record<string, { label: string; color: "blue" | "violet" | "grey" }> = {
  llm: { label: "LLM", color: "blue" },
  embedding: { label: "Embedding", color: "violet" },
  reranker: { label: "Reranker", color: "grey" },
}

// ─── Providers Tab ───────────────────────────────────────────────

function ProvidersTab() {
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [providerTypes, setProviderTypes] = useState<ProviderTypeSchema[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; msg: string }>>({})

  // Dialog
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState<ModelProvider | null>(null)
  const [formName, setFormName] = useState("")
  const [formType, setFormType] = useState("")
  const [formValues, setFormValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  const typeSchema = useMemo(
    () => providerTypes.find((t) => t.type === formType),
    [providerTypes, formType],
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [provRes, types] = await Promise.all([
        modelApi.list(),
        modelApi.listProviderTypes().catch(() => [] as ProviderTypeSchema[]),
      ])
      setProviders(Array.isArray(provRes) ? provRes : (provRes as any).items ?? [])
      setProviderTypes(types)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function openCreate() {
    setEditingProvider(null)
    setFormName("")
    setFormType("")
    setFormValues({})
    setDialogOpen(true)
  }

  function openEdit(p: ModelProvider) {
    setEditingProvider(p)
    setFormName(p.name)
    setFormType(p.type)
    const values: Record<string, string> = {
      api_key: p.api_key ?? "",
      base_url: p.base_url ?? "",
    }
    for (const [k, v] of Object.entries(p.extra_config ?? {})) {
      if (typeof v === "string") values[k] = v
    }
    setFormValues(values)
    setDialogOpen(true)
  }

  function handleTypeChange(val: string) {
    setFormType(val)
    const schema = providerTypes.find((t) => t.type === val)
    if (!schema) return
    setFormValues((prev) => {
      const next = { ...prev }
      for (const f of schema.fields) {
        if (f.default && !next[f.name]) next[f.name] = f.default
      }
      return next
    })
  }

  async function handleSave() {
    setSaving(true)
    try {
      const extra: Record<string, string> = {}
      for (const f of typeSchema?.fields ?? []) {
        if (f.name === "api_key" || f.name === "base_url") continue
        const v = (formValues[f.name] ?? "").trim()
        if (v) extra[f.name] = v
      }

      if (editingProvider) {
        const patch: Record<string, unknown> = {}
        const name = formName.trim()
        if (name !== editingProvider.name) patch.name = name
        if (formType !== editingProvider.type) patch.type = formType
        const baseUrl = (formValues.base_url ?? "").trim()
        if (baseUrl !== (editingProvider.base_url ?? "")) patch.base_url = baseUrl || null
        const apiKey = (formValues.api_key ?? "").trim()
        if (apiKey !== (editingProvider.api_key ?? "")) patch.api_key = apiKey || null
        const origExtra = (editingProvider.extra_config ?? {}) as Record<string, unknown>
        if (JSON.stringify(extra) !== JSON.stringify(origExtra)) patch.extra_config = extra
        if (Object.keys(patch).length === 0) {
          toast.info("没有可保存的修改")
          return
        }
        await modelApi.update(editingProvider.id, patch)
        toast.success("供应商已更新")
      } else {
        await modelApi.create({
          name: formName.trim(),
          type: formType,
          base_url: (formValues.base_url ?? "").trim() || undefined,
          api_key: (formValues.api_key ?? "").trim() || undefined,
          extra_config: Object.keys(extra).length > 0 ? extra : undefined,
        })
        toast.success("供应商已创建")
      }
      setDialogOpen(false)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  async function handleTest(id: string) {
    setTestingId(id)
    try {
      const r = await modelApi.test(id)
      const tested = [r.llm, r.embedding].filter((s) => s === "ok").length
      const errored = [r.llm, r.embedding].filter((s) => s === "error").length
      const ok = errored === 0 && tested > 0
      const parts: string[] = []
      parts.push(`LLM: ${labelStatus(r.llm)}${r.llm_detail ? ` — ${r.llm_detail}` : ""}`)
      parts.push(`Embedding: ${labelStatus(r.embedding)}${r.embedding_detail ? ` — ${r.embedding_detail}` : ""}`)
      setTestResults((prev) => ({ ...prev, [id]: { ok, msg: parts.join(" · ") } }))
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [id]: { ok: false, msg: err instanceof Error ? err.message : "测试失败" },
      }))
    } finally {
      setTestingId(null)
    }
  }

  function labelStatus(s: string) {
    return s === "ok" ? "通过" : s === "error" ? "失败" : s === "skipped" ? "未注册" : s
  }

  async function handleDelete() {
    if (!deleteTarget) return
    await modelApi.delete(deleteTarget)
    load()
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">供应商列表</h2>
        <Button theme="solid" type="primary" icon={<Plus className="size-4" />} onClick={openCreate}>
          添加供应商
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {providers.map((p) => (
          <Card
            key={p.id}
            title={
              <div className="flex items-center gap-2">
                <span>{p.name}</span>
                <Tag>{p.type}</Tag>
              </div>
            }
          >
            <p className="mb-3 text-xs text-muted-foreground">
              创建于 {new Date(p.created_at).toLocaleDateString("zh-CN")}
            </p>
            <div className="flex flex-wrap items-center gap-1">
              <Button theme="borderless" icon={<Pencil className="size-3.5" />} onClick={() => openEdit(p)}>
                编辑
              </Button>
              <Button
                theme="borderless"
                icon={
                  testingId === p.id
                    ? <Loader2 className="size-3.5 animate-spin" />
                    : <PlayCircle className="size-3.5" />
                }
                onClick={() => handleTest(p.id)}
                disabled={testingId === p.id}
              >
                测试连接
              </Button>
              <Button
                theme="borderless"
                icon={<Trash2 className="size-3.5" />}
                onClick={() => setDeleteTarget(p.id)}
              />
            </div>
            {testResults[p.id] && (
              <div className="mt-2 flex items-center gap-1.5 text-xs">
                {testResults[p.id].ok
                  ? <CheckCircle2 className="size-3.5 text-green-500" />
                  : <XCircle className="size-3.5 text-red-500" />}
                <span>{testResults[p.id].msg}</span>
              </div>
            )}
          </Card>
        ))}
      </div>

      <Modal
        visible={dialogOpen}
        onCancel={() => setDialogOpen(false)}
        onOk={handleSave}
        title={editingProvider ? "编辑供应商" : "添加供应商"}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        okButtonProps={{ disabled: !formName || !formType || saving }}
        maskClosable={false}
      >
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">名称</label>
              <Input value={formName} onChange={setFormName} placeholder="My Provider" />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">类型</label>
              <Select
                value={formType || undefined}
                onChange={(v) => v && handleTypeChange(v as string)}
                placeholder="选择供应商类型"
              >
                {providerTypes.map((t) => (
                  <Select.Option key={t.type} value={t.type}>{t.label}</Select.Option>
                ))}
              </Select>
            </div>
          </div>
          {typeSchema?.fields.map((f) => (
            <div key={f.name} className="flex flex-col gap-2">
              <label className="text-sm font-medium">
                {f.label ?? f.name}
                {f.required && <span className="ml-1 text-red-500">*</span>}
              </label>
              <Input
                value={formValues[f.name] ?? ""}
                onChange={(value) => setFormValues((prev) => ({ ...prev, [f.name]: value }))}
                placeholder={f.placeholder ?? f.default ?? ""}
              />
            </div>
          ))}
        </div>
      </Modal>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除供应商"
        description="确认删除此模型供应商？使用该供应商的智能体将无法正常运行。"
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}

// ─── Models Tab ──────────────────────────────────────────────────

function ModelsTab() {
  const [entries, setEntries] = useState<RegistryEntry[]>([])
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [loading, setLoading] = useState(true)

  const [defaultLlmId, setDefaultLlmId] = useState("")
  const [defaultEmbId, setDefaultEmbId] = useState("")
  const [savingDefaults, setSavingDefaults] = useState(false)
  const [defaultsJustSaved, setDefaultsJustSaved] = useState(false)

  const [filterType, setFilterType] = useState("")
  const [filterProvider, setFilterProvider] = useState("")
  const [searchText, setSearchText] = useState("")

  const [editingAlias, setEditingAlias] = useState<string | null>(null)
  const [aliasValue, setAliasValue] = useState("")

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const [addOpen, setAddOpen] = useState(false)
  const [addProviderId, setAddProviderId] = useState("")
  const [addModelType, setAddModelType] = useState<"llm" | "embedding" | "reranker">("llm")
  const [discoveredModels, setDiscoveredModels] = useState<Array<{ id: string; type_hint: string }>>([])
  const [selectedModelIds, setSelectedModelIds] = useState<Set<string>>(new Set())
  const [discovering, setDiscovering] = useState(false)
  const [addSaving, setAddSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [reg, provRes, settings] = await Promise.all([
        modelApi.listRegistry(),
        modelApi.list(),
        systemApi.getSettings().catch(() => ({} as Record<string, unknown>)),
      ])
      setEntries(Array.isArray(reg) ? reg : [])
      setProviders(Array.isArray(provRes) ? provRes : (provRes as any).items ?? [])
      if (settings.default_llm_model_id) setDefaultLlmId(settings.default_llm_model_id as string)
      if (settings.default_embedding_model_id) setDefaultEmbId(settings.default_embedding_model_id as string)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const enabledLlms = useMemo(() => entries.filter((e) => e.model_type === "llm" && e.is_enabled), [entries])
  const enabledEmbs = useMemo(() => entries.filter((e) => e.model_type === "embedding" && e.is_enabled), [entries])

  const providerNames = useMemo(() => {
    const map = new Map<string, string>()
    for (const p of providers) map.set(p.id, p.name)
    return map
  }, [providers])

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      if (filterType && filterType !== "all" && e.model_type !== filterType) return false
      if (filterProvider && filterProvider !== "all" && e.provider_id !== filterProvider) return false
      if (searchText) {
        const q = searchText.toLowerCase()
        const name = (e.display_name || e.model_id).toLowerCase()
        if (!name.includes(q) && !e.model_id.toLowerCase().includes(q)) return false
      }
      return true
    })
  }, [entries, filterType, filterProvider, searchText])

  async function handleSaveDefaults() {
    setSavingDefaults(true)
    try {
      await systemApi.updateSettings({
        default_llm_model_id: defaultLlmId || null,
        default_embedding_model_id: defaultEmbId || null,
      })
      setDefaultsJustSaved(true)
      setTimeout(() => setDefaultsJustSaved(false), 1500)
      toast.success("默认模型已保存")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSavingDefaults(false)
    }
  }

  async function handleToggle(entry: RegistryEntry) {
    try {
      const updated = await modelApi.updateRegistryEntry(entry.id, { is_enabled: !entry.is_enabled })
      setEntries((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新失败")
    }
  }

  async function handleSetType(entry: RegistryEntry, next: RegistryEntry["model_type"]) {
    if (next === entry.model_type) return
    try {
      const updated = await modelApi.updateRegistryEntry(entry.id, { model_type: next })
      setEntries((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新失败")
    }
  }

  async function handleSaveAlias(entryId: string) {
    try {
      const updated = await modelApi.updateRegistryEntry(entryId, { display_name: aliasValue.trim() || undefined })
      setEntries((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
      setEditingAlias(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新失败")
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await modelApi.deleteRegistryEntry(deleteTarget)
      setEntries((prev) => prev.filter((e) => e.id !== deleteTarget))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  function openAddDialog() {
    setAddProviderId("")
    setAddModelType("llm")
    setDiscoveredModels([])
    setSelectedModelIds(new Set())
    setAddOpen(true)
  }

  async function handleDiscover() {
    if (!addProviderId) return
    const provider = providers.find((p) => p.id === addProviderId)
    if (!provider) return
    setDiscovering(true)
    try {
      const res = await modelApi.discover({
        type: provider.type,
        base_url: provider.base_url || undefined,
        api_key: provider.api_key || undefined,
      })
      const existingIds = new Set(entries.filter((e) => e.provider_id === addProviderId).map((e) => e.model_id))
      const available = res.models.filter((m) => !existingIds.has(m.id))
      setDiscoveredModels(available)
      setSelectedModelIds(new Set())
      if (available.length === 0) toast.info("该供应商所有模型已注册")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "获取模型失败")
    } finally {
      setDiscovering(false)
    }
  }

  function toggleModelSelection(modelId: string) {
    setSelectedModelIds((prev) => {
      const next = new Set(prev)
      if (next.has(modelId)) next.delete(modelId)
      else next.add(modelId)
      return next
    })
  }

  async function handleAddModels() {
    if (selectedModelIds.size === 0) return
    setAddSaving(true)
    try {
      let added = 0
      const ids = Array.from(selectedModelIds)
      for (const mid of ids) {
        try {
          await modelApi.createRegistryEntry({
            provider_id: addProviderId,
            model_id: mid,
            model_type: addModelType,
            is_enabled: true,
          })
          added++
        } catch { /* skip duplicates */ }
      }
      toast.success(`已添加 ${added} 个模型`)
      setAddOpen(false)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "添加失败")
    } finally {
      setAddSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spin size="large" />
      </div>
    )
  }

  // Table columns
  const columns: ColumnProps<RegistryEntry>[] = [
    {
      title: "启用",
      dataIndex: "is_enabled",
      width: 80,
      align: "center",
      render: (_v, entry) => (
        <Switch checked={entry.is_enabled} onChange={() => handleToggle(entry)} />
      ),
    },
    {
      title: "模型名",
      dataIndex: "model_id",
      render: (text: string) => <span className="font-mono text-xs">{text}</span>,
    },
    {
      title: "别名",
      dataIndex: "display_name",
      render: (_v, entry) => editingAlias === entry.id ? (
        <Input
          value={aliasValue}
          onChange={setAliasValue}
          onBlur={() => handleSaveAlias(entry.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSaveAlias(entry.id)
            if (e.key === "Escape") setEditingAlias(null)
          }}
          autoFocus
          size="small"
        />
      ) : (
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded px-1 text-xs hover:bg-muted"
          onClick={() => { setEditingAlias(entry.id); setAliasValue(entry.display_name || "") }}
        >
          {entry.display_name || <span className="text-muted-foreground">-</span>}
          <Pencil className="size-3 text-muted-foreground" />
        </button>
      ),
    },
    {
      title: "类型",
      dataIndex: "model_type",
      width: 130,
      render: (_v, entry) => (
        <Dropdown
          trigger="click"
          position="bottomLeft"
          render={
            <Dropdown.Menu>
              {(["llm", "embedding", "reranker"] as const).map((t) => (
                <Dropdown.Item
                  key={t}
                  onClick={() => handleSetType(entry, t)}
                  disabled={t === entry.model_type}
                >
                  {t === entry.model_type && <Check className="mr-2 size-3.5 inline" />}
                  <span className={t === entry.model_type ? "" : "ml-[22px]"}>
                    {TYPE_TAG[t].label}
                  </span>
                </Dropdown.Item>
              ))}
            </Dropdown.Menu>
          }
        >
          <button
            type="button"
            className="inline-flex items-center gap-1"
            title="点击切换模型类型"
          >
            <Tag color={TYPE_TAG[entry.model_type]?.color ?? "grey"}>
              {TYPE_TAG[entry.model_type]?.label ?? entry.model_type}
            </Tag>
            <ChevronDown className="size-3 text-muted-foreground" />
          </button>
        </Dropdown>
      ),
    },
    {
      title: "来源",
      dataIndex: "provider_name",
      render: (_v, entry) =>
        <span className="text-xs text-muted-foreground">
          {entry.provider_name || providerNames.get(entry.provider_id) || "-"}
        </span>,
    },
    {
      title: "操作",
      dataIndex: "_op",
      width: 80,
      align: "center",
      render: (_v, entry) => (
        <Button
          theme="borderless"
          icon={<Trash2 className="size-3.5" />}
          onClick={() => setDeleteTarget(entry.id)}
        />
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-6">
      {/* System Defaults */}
      <Card title="默认模型设置">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium">默认 LLM 模型</label>
            <Select
              value={defaultLlmId || undefined}
              onChange={(v) => v != null && setDefaultLlmId(v as string)}
              placeholder="选择默认 LLM"
            >
              {enabledLlms.map((m) => (
                <Select.Option key={m.id} value={m.id}>
                  {m.display_name || m.model_id} ({m.provider_name || providerNames.get(m.provider_id) || "未知"})
                </Select.Option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium">默认 Embedding 模型</label>
            <Select
              value={defaultEmbId || undefined}
              onChange={(v) => v != null && setDefaultEmbId(v as string)}
              placeholder="选择默认 Embedding"
            >
              {enabledEmbs.map((m) => (
                <Select.Option key={m.id} value={m.id}>
                  {m.display_name || m.model_id} ({m.provider_name || providerNames.get(m.provider_id) || "未知"})
                </Select.Option>
              ))}
            </Select>
          </div>
        </div>
        <div className="mt-4">
          <Button
            theme={defaultsJustSaved ? "light" : "solid"}
            type="primary"
            icon={defaultsJustSaved ? <Check className="size-4" /> : <Save className="size-4" />}
            onClick={handleSaveDefaults}
            disabled={savingDefaults || defaultsJustSaved}
          >
            {defaultsJustSaved ? "已保存" : (savingDefaults ? "保存中..." : "保存")}
          </Button>
        </div>
      </Card>

      {/* Model Registry */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">模型注册表</h2>
          <Button theme="solid" type="primary" icon={<Plus className="size-4" />} onClick={openAddDialog}>
            添加模型
          </Button>
        </div>

        {/* Filters */}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Select
            value={filterType || "all"}
            onChange={(v) => setFilterType((v as string) === "all" ? "" : (v as string ?? ""))}
            style={{ width: 144 }}
          >
            <Select.Option value="all">全部类型</Select.Option>
            <Select.Option value="llm">LLM</Select.Option>
            <Select.Option value="embedding">Embedding</Select.Option>
            <Select.Option value="reranker">Reranker</Select.Option>
          </Select>
          <Select
            value={filterProvider || "all"}
            onChange={(v) => setFilterProvider((v as string) === "all" ? "" : (v as string ?? ""))}
            style={{ width: 160 }}
          >
            <Select.Option value="all">全部来源</Select.Option>
            {providers.map((p) => (
              <Select.Option key={p.id} value={p.id}>{p.name}</Select.Option>
            ))}
          </Select>
          <div className="flex-1">
            <Input
              value={searchText}
              onChange={setSearchText}
              placeholder="搜索模型..."
              prefix={<Search className="ml-2 size-4 text-muted-foreground" />}
            />
          </div>
        </div>

        <Table
          columns={columns}
          dataSource={filtered}
          rowKey="id"
          pagination={false}
          empty={entries.length === 0 ? "点击「添加模型」从供应商获取可用模型" : "无匹配结果"}
        />
      </div>

      {/* Add Model Modal */}
      <Modal
        visible={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={handleAddModels}
        title="添加模型"
        confirmLoading={addSaving}
        okText={selectedModelIds.size > 0 ? `添加 ${selectedModelIds.size} 个模型` : "添加"}
        cancelText="取消"
        okButtonProps={{ disabled: selectedModelIds.size === 0 || addSaving }}
        width={680}
        maskClosable={false}
      >
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">选择供应商</label>
              <Select
                value={addProviderId || undefined}
                onChange={(v) => {
                  if (v) {
                    setAddProviderId(v as string)
                    setDiscoveredModels([])
                    setSelectedModelIds(new Set())
                  }
                }}
                placeholder="选择供应商"
              >
                {providers.map((p) => (
                  <Select.Option key={p.id} value={p.id}>{p.name} ({p.type})</Select.Option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">模型类型</label>
              <Select
                value={addModelType}
                onChange={(v) => v && setAddModelType(v as "llm" | "embedding" | "reranker")}
              >
                <Select.Option value="llm">LLM</Select.Option>
                <Select.Option value="embedding">Embedding</Select.Option>
                <Select.Option value="reranker">Reranker</Select.Option>
              </Select>
            </div>
          </div>

          <Button
            theme="light"
            icon={discovering ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
            onClick={handleDiscover}
            disabled={!addProviderId || discovering}
          >
            {discovering ? "获取中..." : "获取模型列表"}
          </Button>

          {discoveredModels.length > 0 && (
            <div className="rounded-lg border">
              <div className="flex items-center justify-between border-b px-3 py-2">
                <span className="text-xs text-muted-foreground">
                  {discoveredModels.length} 个可用模型，已选 {selectedModelIds.size} 个
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-xs text-primary hover:underline"
                    onClick={() => setSelectedModelIds(new Set(discoveredModels.map((m) => m.id)))}
                  >
                    全选
                  </button>
                  <button
                    type="button"
                    className="text-xs text-primary hover:underline"
                    onClick={() => setSelectedModelIds(new Set())}
                  >
                    全不选
                  </button>
                </div>
              </div>
              <div className="max-h-80 overflow-y-auto p-1">
                {discoveredModels.map((m) => (
                  <label
                    key={m.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted"
                  >
                    <input
                      type="checkbox"
                      checked={selectedModelIds.has(m.id)}
                      onChange={() => toggleModelSelection(m.id)}
                      className="size-3.5 rounded border-border"
                    />
                    <span className="flex-1 truncate font-mono text-xs" title={m.id}>{m.id}</span>
                    <Tag size="small">{m.type_hint}</Tag>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除模型"
        description="确认删除此模型注册？引用该模型的智能体和知识库将受影响。"
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}

// ─── Page Root ───────────────────────────────────────────────────

export default function ModelsPage() {
  return (
    <Tabs type="line">
      <TabPane tab="供应商管理" itemKey="providers">
        <div className="mt-4">
          <ProvidersTab />
        </div>
      </TabPane>
      <TabPane tab="模型管理" itemKey="models">
        <div className="mt-4">
          <ModelsTab />
        </div>
      </TabPane>
    </Tabs>
  )
}
