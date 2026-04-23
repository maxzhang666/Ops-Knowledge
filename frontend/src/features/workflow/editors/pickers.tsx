/**
 * UUID pickers for workflow node config — replace raw-UUID Input fields with
 * real dropdowns populated from the platform's own resource lists.
 *
 * Without these, LLM / Classifier / Extractor / KnowledgeRetrieval nodes
 * require users to copy-paste UUIDs, which makes the editor unusable.
 */
import { useEffect, useState } from "react"
import { Input } from "@/components/ui/input"
import { modelApi, type ModelProvider, type RegistryEntry } from "@/api/model"
import { knowledgeApi } from "@/api/knowledge"


export function ModelProviderPicker({
  value,
  onChange,
}: {
  value: string | undefined
  onChange: (v: string) => void
}) {
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    modelApi.list()
      .then(setProviders)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-xs text-muted-foreground">加载模型供应商...</p>

  if (providers.length === 0) {
    return (
      <p className="rounded-md border border-dashed bg-muted/30 p-2 text-xs text-muted-foreground">
        未配置任何模型供应商。请先前往 设置 → 模型供应商 配置。
      </p>
    )
  }

  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
    >
      <option value="">-- 选择供应商 --</option>
      {providers.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name} ({p.type})
        </option>
      ))}
    </select>
  )
}


/**
 * 统一模型选择器 — 从系统模型登记表（/model/registry）拉取启用的条目，
 * 合并 provider + model 为一次选择，onChange 回传 (providerId, modelName)。
 *
 * 兼容 fallback：若 registry 接口为空或失败，回退到 provider.models_available。
 * 这样无论用户通过"发现模型"（registry）还是在 provider 详情里写死 models_available
 * 都能正确识别。
 */
export function LLMModelPicker({
  providerId,
  modelName,
  onChange,
  kind = "llm",
}: {
  providerId: string | undefined
  modelName: string | undefined
  onChange: (providerId: string, modelName: string) => void
  kind?: "llm" | "embedding" | "reranker"
}) {
  const [entries, setEntries] = useState<
    Array<{ providerId: string; providerName: string; providerType: string; modelId: string }>
  >([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const [registry, providers] = await Promise.all([
          modelApi.listRegistry().catch(() => [] as RegistryEntry[]),
          modelApi.list().catch(() => [] as ModelProvider[]),
        ])
        if (!alive) return
        const providerById = new Map(providers.map((p) => [p.id, p]))
        const flat: typeof entries = []

        // 主源：registry —— 用户主动维护/启用的模型条目
        for (const r of registry) {
          if (r.model_type !== kind || r.is_enabled === false) continue
          const p = providerById.get(r.provider_id)
          flat.push({
            providerId: r.provider_id,
            providerName: r.provider_name ?? p?.name ?? "未知供应商",
            providerType: p?.type ?? "",
            modelId: r.model_id,
          })
        }

        // 回退源：provider.models_available（老数据 / registry 尚未同步）
        if (flat.length === 0) {
          for (const p of providers) {
            if (p.is_active === false) continue
            const list = (p.models_available?.[kind] ?? []) as string[]
            for (const m of list) {
              flat.push({
                providerId: p.id,
                providerName: p.name,
                providerType: p.type,
                modelId: m,
              })
            }
          }
        }

        setEntries(flat)
      } finally {
        if (alive) setLoading(false)
      }
    }
    load()
    return () => { alive = false }
  }, [kind])

  if (loading) return <p className="text-xs text-muted-foreground">加载模型...</p>

  if (entries.length === 0) {
    return (
      <p className="rounded-md border border-dashed bg-muted/30 p-2 text-xs text-muted-foreground">
        尚无可用{kind === "llm" ? "大模型" : kind === "embedding" ? "向量模型" : "重排模型"}，
        请先在 设置 → 模型 配置。
      </p>
    )
  }

  // 按 provider 分组后用于 optgroup
  const groups = new Map<string, { label: string; items: typeof entries }>()
  for (const e of entries) {
    const key = e.providerId
    if (!groups.has(key)) {
      groups.set(key, {
        label: e.providerType ? `${e.providerName}（${e.providerType}）` : e.providerName,
        items: [],
      })
    }
    groups.get(key)!.items.push(e)
  }

  const currentKey = providerId && modelName ? `${providerId}::${modelName}` : ""

  return (
    <select
      value={currentKey}
      onChange={(e) => {
        const [pid, mn] = e.target.value.split("::")
        if (pid && mn) onChange(pid, mn)
      }}
      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
    >
      <option value="">-- 选择模型 --</option>
      {Array.from(groups.entries()).map(([pid, g]) => (
        <optgroup key={pid} label={g.label}>
          {g.items.map((e) => (
            <option key={`${e.providerId}::${e.modelId}`} value={`${e.providerId}::${e.modelId}`}>
              {e.modelId}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}


export function ModelNamePicker({
  providerId,
  value,
  kind = "llm",
  onChange,
}: {
  providerId: string | undefined
  value: string | undefined
  kind?: "llm" | "embedding" | "reranker"
  onChange: (v: string) => void
}) {
  const [models, setModels] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!providerId) {
      setModels([])
      return
    }
    setLoading(true)
    modelApi.get(providerId)
      .then((p) => {
        const list = (p.models_available?.[kind] ?? []) as string[]
        setModels(list)
      })
      .catch(() => setModels([]))
      .finally(() => setLoading(false))
  }, [providerId, kind])

  if (!providerId) {
    return (
      <Input value={value ?? ""} disabled placeholder="请先选择供应商" className="text-xs" />
    )
  }
  if (loading) return <p className="text-xs text-muted-foreground">加载模型...</p>

  if (models.length === 0) {
    // Provider has no discovered models — fall back to free text so users can
    // still type one in (e.g. for Ollama providers that list nothing).
    return (
      <Input
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder="该供应商未发现模型，手动输入"
        className="text-xs"
      />
    )
  }

  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
    >
      <option value="">-- 选择模型 --</option>
      {models.map((m) => (
        <option key={m} value={m}>{m}</option>
      ))}
    </select>
  )
}


interface KBSummary {
  id: string
  name: string
  document_count?: number
  chunk_count?: number
}


export function FolderPicker({
  kbIds,
  value,
  onChange,
}: {
  kbIds: string[]
  value: string[] | undefined
  onChange: (v: string[]) => void
}) {
  const [folders, setFolders] = useState<Array<{ id: string; name: string; kbName: string }>>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!kbIds || kbIds.length === 0) {
      setFolders([])
      return
    }
    setLoading(true)
    Promise.all(
      kbIds.map(async (kbId) => {
        try {
          const items = await knowledgeApi.listFolders(kbId)
          const kb = await knowledgeApi.getKB(kbId).catch(() => ({ name: kbId.slice(0, 8) }))
          return { kb, items }
        } catch {
          return { kb: { name: kbId.slice(0, 8) }, items: [] as Array<{ id: string; name: string }> }
        }
      }),
    )
      .then((results) => {
        const flat: Array<{ id: string; name: string; kbName: string }> = []
        for (const r of results) {
          for (const f of r.items) {
            flat.push({ id: f.id, name: f.name, kbName: r.kb.name ?? "KB" })
          }
        }
        setFolders(flat)
      })
      .finally(() => setLoading(false))
  }, [kbIds.join(",")])  // eslint-disable-line react-hooks/exhaustive-deps

  if (!kbIds || kbIds.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        请先选择上方的知识库；文件夹范围会基于其内容加载
      </p>
    )
  }
  if (loading) return <p className="text-xs text-muted-foreground">加载文件夹...</p>
  if (folders.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">选定知识库下没有文件夹（留空 = 全部检索）</p>
    )
  }

  const selected = new Set(value ?? [])

  function toggle(id: string) {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange(Array.from(next))
  }

  return (
    <div className="max-h-48 overflow-y-auto rounded-md border p-2">
      {folders.map((f) => (
        <label
          key={f.id}
          className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted"
        >
          <input
            type="checkbox"
            checked={selected.has(f.id)}
            onChange={() => toggle(f.id)}
          />
          <span className="flex-1 truncate">
            <span className="text-muted-foreground">{f.kbName} / </span>
            {f.name}
          </span>
        </label>
      ))}
      <div className="mt-1 px-2 text-[10px] text-muted-foreground">
        已选 {selected.size} 个（留空 = 全部文件夹）
      </div>
    </div>
  )
}


export function KnowledgeBasePicker({
  value,
  onChange,
  multi = true,
}: {
  value: string[] | undefined
  onChange: (v: string[]) => void
  multi?: boolean
}) {
  const [kbs, setKbs] = useState<KBSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    knowledgeApi.listKBs()
      .then((res) => {
        // Backend shape: PaginatedResponse<KnowledgeBase>; tolerate both
        // direct array and {items: [...]} wrappers without failing.
        const items =
          Array.isArray(res)
            ? res
            : (res as { items?: KBSummary[] })?.items ?? []
        setKbs(items)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-xs text-muted-foreground">加载知识库...</p>

  if (kbs.length === 0) {
    return (
      <p className="rounded-md border border-dashed bg-muted/30 p-2 text-xs text-muted-foreground">
        还没有知识库，请先在 知识库 页面创建。
      </p>
    )
  }

  const selected = new Set(value ?? [])

  function toggle(id: string) {
    const next = new Set(selected)
    if (next.has(id)) {
      next.delete(id)
    } else {
      if (!multi) next.clear()
      next.add(id)
    }
    onChange(Array.from(next))
  }

  return (
    <div className="max-h-60 overflow-y-auto rounded-md border p-2">
      {kbs.map((k) => (
        <label
          key={k.id}
          className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted"
        >
          <input
            type={multi ? "checkbox" : "radio"}
            checked={selected.has(k.id)}
            onChange={() => toggle(k.id)}
          />
          <span className="flex-1 truncate">{k.name}</span>
          {k.document_count !== undefined && (
            <span className="text-muted-foreground">{k.document_count} 文档</span>
          )}
        </label>
      ))}
      <div className="mt-1 px-2 text-[10px] text-muted-foreground">
        已选 {selected.size} 个
      </div>
    </div>
  )
}
