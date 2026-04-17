import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Plus, Trash2, PlayCircle, CheckCircle2, XCircle, Loader2,
  Save, Pencil, Search, Check,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { modelApi, type ModelProvider, type ProviderTypeSchema, type RegistryEntry } from "@/api/model"
import { systemApi } from "@/api/system"

const TYPE_BADGE: Record<string, { label: string; variant: "default" | "secondary" | "outline" }> = {
  llm: { label: "LLM", variant: "default" },
  embedding: { label: "Embedding", variant: "secondary" },
  reranker: { label: "Reranker", variant: "outline" },
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
  // Values keyed by backend field name (api_key, base_url, api_version, ...)
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
    // Seed fields with declared defaults unless user already entered something
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
      // Pack non-core fields (api_version, etc.) into extra_config
      const extra: Record<string, string> = {}
      for (const f of typeSchema?.fields ?? []) {
        if (f.name === "api_key" || f.name === "base_url") continue
        const v = (formValues[f.name] ?? "").trim()
        if (v) extra[f.name] = v
      }

      if (editingProvider) {
        // PATCH — send only the fields the user actually changed. Backend
        // schema has extra=forbid so undeclared keys return 422 instead of
        // being silently dropped.
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
        // POST — create path uses full payload (required fields + optionals).
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
      // "error" is definitely a fail. "skipped" means no model of that type
      // is registered — not a failure (provider may only offer LLM, etc.).
      // Green only if at least one capability tested OK and none errored.
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

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">供应商列表</h2>
        <Button onClick={openCreate}>
          <Plus className="mr-1 size-4" /> 添加供应商
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {providers.map((p) => (
          <Card key={p.id} size="sm">
            <CardHeader className="pb-2">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">{p.name}</CardTitle>
                <Badge variant="secondary">{p.type}</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-xs text-muted-foreground">
                创建于 {new Date(p.created_at).toLocaleDateString("zh-CN")}
              </p>
              <div className="flex flex-wrap items-center gap-1">
                <Button variant="ghost" size="sm" onClick={() => openEdit(p)}>
                  <Pencil className="mr-1 size-3.5" /> 编辑
                </Button>
                <Button variant="ghost" size="sm" onClick={() => handleTest(p.id)} disabled={testingId === p.id}>
                  {testingId === p.id
                    ? <Loader2 className="mr-1 size-3.5 animate-spin" />
                    : <PlayCircle className="mr-1 size-3.5" />}
                  测试连接
                </Button>
                {/* Models are managed via the Models tab — no sync button here */}
                <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(p.id)}>
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
              {testResults[p.id] && (
                <div className="mt-2 flex items-center gap-1.5 text-xs">
                  {testResults[p.id].ok
                    ? <CheckCircle2 className="size-3.5 text-green-500" />
                    : <XCircle className="size-3.5 text-red-500" />}
                  <span>{testResults[p.id].msg}</span>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Create / Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(v) => { if (!v) setDialogOpen(false) }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingProvider ? "编辑供应商" : "添加供应商"}</DialogTitle>
            <DialogDescription>
              {editingProvider ? "修改供应商配置" : "配置新的模型 API 供应商"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label>名称</Label>
                <Input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="My Provider" />
              </div>
              <div className="flex flex-col gap-2">
                <Label>类型</Label>
                <Select value={formType || undefined} onValueChange={(v) => v && handleTypeChange(v)}>
                  <SelectTrigger className="w-full">
                    {formType
                      ? <span>{providerTypes.find((t) => t.type === formType)?.label ?? formType}</span>
                      : <SelectValue placeholder="选择供应商类型" />}
                  </SelectTrigger>
                  <SelectContent>
                    {providerTypes.map((t) => (
                      <SelectItem key={t.type} value={t.type}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {typeSchema?.fields.map((f) => (
              <div key={f.name} className="flex flex-col gap-2">
                <Label>
                  {f.label ?? f.name}
                  {f.required && <span className="ml-1 text-destructive">*</span>}
                </Label>
                <Input
                  type={f.type === "password" ? "text" : f.type === "url" ? "url" : "text"}
                  value={formValues[f.name] ?? ""}
                  onChange={(e) => setFormValues((prev) => ({ ...prev, [f.name]: e.target.value }))}
                  placeholder={f.placeholder ?? f.default ?? ""}
                />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>取消</Button>
            <Button onClick={handleSave} disabled={!formName || !formType || saving}>
              {saving ? "保存中..." : "保存"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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

  // Defaults
  const [defaultLlmId, setDefaultLlmId] = useState("")
  const [defaultEmbId, setDefaultEmbId] = useState("")
  const [savingDefaults, setSavingDefaults] = useState(false)
  const [defaultsJustSaved, setDefaultsJustSaved] = useState(false)

  // Filters
  const [filterType, setFilterType] = useState("")
  const [filterProvider, setFilterProvider] = useState("")
  const [searchText, setSearchText] = useState("")

  // Inline edit
  const [editingAlias, setEditingAlias] = useState<string | null>(null)
  const [aliasValue, setAliasValue] = useState("")

  // Delete
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  // Add model dialog
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

  async function handleCycleType(entry: RegistryEntry) {
    const order: RegistryEntry["model_type"][] = ["llm", "embedding", "reranker"]
    const next = order[(order.indexOf(entry.model_type) + 1) % order.length]
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
      // Filter out already-registered models for this provider
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

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div className="flex flex-col gap-6">
      {/* System Defaults */}
      <Card>
        <CardHeader>
          <CardTitle>默认模型设置</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label>默认 LLM 模型</Label>
              <Select value={defaultLlmId || undefined} onValueChange={(v) => v != null && setDefaultLlmId(v)}>
                <SelectTrigger className="w-full">
                  {defaultLlmId
                    ? <span className="truncate">{(() => { const m = enabledLlms.find((e) => e.id === defaultLlmId); return m ? `${m.display_name || m.model_id} (${m.provider_name || "未知"})` : defaultLlmId })()}</span>
                    : <SelectValue placeholder="选择默认 LLM" />}
                </SelectTrigger>
                <SelectContent>
                  {enabledLlms.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.display_name || m.model_id} ({m.provider_name || providerNames.get(m.provider_id) || "未知"})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label>默认 Embedding 模型</Label>
              <Select value={defaultEmbId || undefined} onValueChange={(v) => v != null && setDefaultEmbId(v)}>
                <SelectTrigger className="w-full">
                  {defaultEmbId
                    ? <span className="truncate">{(() => { const m = enabledEmbs.find((e) => e.id === defaultEmbId); return m ? `${m.display_name || m.model_id} (${m.provider_name || "未知"})` : defaultEmbId })()}</span>
                    : <SelectValue placeholder="选择默认 Embedding" />}
                </SelectTrigger>
                <SelectContent>
                  {enabledEmbs.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.display_name || m.model_id} ({m.provider_name || providerNames.get(m.provider_id) || "未知"})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button
            className="mt-4"
            onClick={handleSaveDefaults}
            disabled={savingDefaults || defaultsJustSaved}
            variant={defaultsJustSaved ? "outline" : "default"}
          >
            {defaultsJustSaved
              ? <><Check className="mr-1 size-4 text-success" /> <span className="text-success">已保存</span></>
              : <><Save className="mr-1 size-4" /> {savingDefaults ? "保存中..." : "保存"}</>}
          </Button>
        </CardContent>
      </Card>

      {/* Model Registry Table */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">模型注册表</h2>
          <Button onClick={openAddDialog}>
            <Plus className="mr-1 size-4" /> 添加模型
          </Button>
        </div>

        {/* Filters */}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Select value={filterType || "all"} onValueChange={(v) => setFilterType(v === "all" ? "" : (v ?? ""))}>
            <SelectTrigger className="w-36">
              {filterType && filterType !== "all"
                ? <span>{TYPE_BADGE[filterType]?.label ?? filterType}</span>
                : <span>全部类型</span>}
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部类型</SelectItem>
              <SelectItem value="llm">LLM</SelectItem>
              <SelectItem value="embedding">Embedding</SelectItem>
              <SelectItem value="reranker">Reranker</SelectItem>
            </SelectContent>
          </Select>
          <Select value={filterProvider || "all"} onValueChange={(v) => setFilterProvider(v === "all" ? "" : (v ?? ""))}>
            <SelectTrigger className="w-40">
              {filterProvider && filterProvider !== "all"
                ? <span className="truncate">{providers.find(p => p.id === filterProvider)?.name ?? filterProvider}</span>
                : <span>全部来源</span>}
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部来源</SelectItem>
              {providers.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="搜索模型..."
              className="pl-8"
            />
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
            {entries.length === 0 ? "点击「添加模型」从供应商获取可用模型" : "无匹配结果"}
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-xs font-medium text-muted-foreground">
                  <th className="w-16 px-3 py-2 text-center">启用</th>
                  <th className="px-3 py-2">模型名</th>
                  <th className="px-3 py-2">别名</th>
                  <th className="w-28 px-3 py-2">类型</th>
                  <th className="px-3 py-2">来源</th>
                  <th className="w-16 px-3 py-2 text-center">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((entry) => (
                  <tr key={entry.id} className="border-b last:border-b-0 hover:bg-muted/30">
                    <td className="px-3 py-2 text-center">
                      <Switch
                        checked={entry.is_enabled}
                        onCheckedChange={() => handleToggle(entry)}
                      />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{entry.model_id}</td>
                    <td className="px-3 py-2">
                      {editingAlias === entry.id ? (
                        <Input
                          value={aliasValue}
                          onChange={(e) => setAliasValue(e.target.value)}
                          onBlur={() => handleSaveAlias(entry.id)}
                          onKeyDown={(e) => { if (e.key === "Enter") handleSaveAlias(entry.id); if (e.key === "Escape") setEditingAlias(null) }}
                          className="h-7 text-xs"
                          autoFocus
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
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <button type="button" onClick={() => handleCycleType(entry)}>
                        <Badge variant={TYPE_BADGE[entry.model_type]?.variant ?? "secondary"}>
                          {TYPE_BADGE[entry.model_type]?.label ?? entry.model_type}
                        </Badge>
                      </button>
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {entry.provider_name || providerNames.get(entry.provider_id) || "-"}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(entry.id)}>
                        <Trash2 className="size-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Model Dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>添加模型</DialogTitle>
            <DialogDescription>从已配置的供应商中获取并添加模型</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label>选择供应商</Label>
                <Select value={addProviderId || undefined} onValueChange={(v) => { if (v) { setAddProviderId(v); setDiscoveredModels([]); setSelectedModelIds(new Set()) } }}>
                  <SelectTrigger className="w-full">
                    {addProviderId
                      ? <span className="truncate">{providers.find((p) => p.id === addProviderId)?.name ?? addProviderId}</span>
                      : <SelectValue placeholder="选择供应商" />}
                  </SelectTrigger>
                  <SelectContent>
                    {providers.map((p) => (
                      <SelectItem key={p.id} value={p.id}>{p.name} ({p.type})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label>模型类型</Label>
                <Select value={addModelType} onValueChange={(v) => v && setAddModelType(v as "llm" | "embedding" | "reranker")}>
                  <SelectTrigger className="w-full">
                    {addModelType
                      ? <span>{TYPE_BADGE[addModelType]?.label ?? addModelType}</span>
                      : <SelectValue />}
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="llm">LLM</SelectItem>
                    <SelectItem value="embedding">Embedding</SelectItem>
                    <SelectItem value="reranker">Reranker</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Button
              variant="outline"
              onClick={handleDiscover}
              disabled={!addProviderId || discovering}
            >
              {discovering
                ? <Loader2 className="mr-1 size-4 animate-spin" />
                : <Search className="mr-1 size-4" />}
              {discovering ? "获取中..." : "获取模型列表"}
            </Button>

            {discoveredModels.length > 0 && (
              <div className="rounded-lg border">
                <div className="flex items-center justify-between border-b px-3 py-2">
                  <span className="text-xs text-muted-foreground">
                    {discoveredModels.length} 个可用模型，已选 {selectedModelIds.size} 个
                  </span>
                  <div className="flex gap-2">
                    <button type="button" className="text-xs text-primary hover:underline" onClick={() => setSelectedModelIds(new Set(discoveredModels.map((m) => m.id)))}>
                      全选
                    </button>
                    <button type="button" className="text-xs text-primary hover:underline" onClick={() => setSelectedModelIds(new Set())}>
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
                      <Badge variant="outline" className="text-[10px]">{m.type_hint}</Badge>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>取消</Button>
            <Button onClick={handleAddModels} disabled={selectedModelIds.size === 0 || addSaving}>
              {addSaving ? "添加中..." : `添加 ${selectedModelIds.size} 个模型`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
    <Tabs defaultValue="providers">
      <TabsList variant="line">
        <TabsTrigger value="providers">供应商管理</TabsTrigger>
        <TabsTrigger value="models">模型管理</TabsTrigger>
      </TabsList>
      <TabsContent value="providers">
        <div className="mt-4">
          <ProvidersTab />
        </div>
      </TabsContent>
      <TabsContent value="models">
        <div className="mt-4">
          <ModelsTab />
        </div>
      </TabsContent>
    </Tabs>
  )
}
