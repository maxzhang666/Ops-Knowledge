import { useState } from "react"
import { Loader2, Search, CheckCircle2, XCircle, Database, HardDrive } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import { modelApi } from "@/api/model"
import { systemApi } from "@/api/system"

const PROVIDER_TYPES = [
  { value: "openai", label: "OpenAI", needsKey: true, needsUrl: false, defaultUrl: "https://api.openai.com" },
  { value: "anthropic", label: "Anthropic", needsKey: true, needsUrl: false, defaultUrl: "" },
  { value: "ollama", label: "Ollama", needsKey: false, needsUrl: true, defaultUrl: "http://localhost:11434" },
  { value: "azure", label: "Azure OpenAI", needsKey: true, needsUrl: true, defaultUrl: "" },
  { value: "deepseek", label: "DeepSeek", needsKey: true, needsUrl: false, defaultUrl: "https://api.deepseek.com" },
  { value: "openrouter", label: "OpenRouter", needsKey: true, needsUrl: false, defaultUrl: "" },
] as const

interface DiscoveredModel {
  id: string
  category: "llm" | "embedding" | "reranker"
  checked: boolean
}

interface StepProps {
  onNext: () => void
  onBack?: () => void
}

type TestStatus = "idle" | "testing" | "ok" | "fail"

export function StepProvider({ onNext, onBack }: StepProps) {
  // Milvus config
  const [milvusUri, setMilvusUri] = useState("http://localhost:19530")
  const [milvusToken, setMilvusToken] = useState("")
  const [milvusTest, setMilvusTest] = useState<TestStatus>("idle")
  const [milvusDetail, setMilvusDetail] = useState("")

  // MinIO config
  const [minioEndpoint, setMinioEndpoint] = useState("localhost:9000")
  const [minioAccessKey, setMinioAccessKey] = useState("minioadmin")
  const [minioSecretKey, setMinioSecretKey] = useState("minioadmin")
  const [minioBucket, setMinioBucket] = useState("ops-knowledge-docs")
  const [minioSecure, setMinioSecure] = useState(false)
  const [minioTest, setMinioTest] = useState<TestStatus>("idle")
  const [minioDetail, setMinioDetail] = useState("")

  // Infra saving
  const [savingInfra, setSavingInfra] = useState(false)
  const [infraSaved, setInfraSaved] = useState(false)

  // LLM Provider
  const [name, setName] = useState("")
  const [type, setType] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [models, setModels] = useState<DiscoveredModel[]>([])
  const [discovering, setDiscovering] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testOk, setTestOk] = useState<boolean | null>(null)
  const [testMsg, setTestMsg] = useState("")

  const typeDef = PROVIDER_TYPES.find((t) => t.value === type)

  async function handleTestMilvus() {
    setMilvusTest("testing")
    setMilvusDetail("")
    try {
      const res = await systemApi.testConnection("milvus", { uri: milvusUri, token: milvusToken || undefined })
      setMilvusTest(res.ok ? "ok" : "fail")
      if (!res.ok) setMilvusDetail(res.detail || "连接失败")
    } catch (e) {
      setMilvusTest("fail")
      setMilvusDetail(e instanceof Error ? e.message : "连接失败")
    }
  }

  async function handleTestMinio() {
    setMinioTest("testing")
    setMinioDetail("")
    try {
      const res = await systemApi.testConnection("minio", {
        endpoint: minioEndpoint, access_key: minioAccessKey,
        secret_key: minioSecretKey, bucket: minioBucket, secure: minioSecure,
      })
      setMinioTest(res.ok ? "ok" : "fail")
      if (!res.ok) setMinioDetail(res.detail || "连接失败")
    } catch (e) {
      setMinioTest("fail")
      setMinioDetail(e instanceof Error ? e.message : "连接失败")
    }
  }

  async function handleSaveInfra() {
    setSavingInfra(true)
    try {
      await systemApi.updateSettings({
        milvus: { uri: milvusUri, token: milvusToken || undefined },
        minio: {
          endpoint: minioEndpoint, access_key: minioAccessKey,
          secret_key: minioSecretKey, bucket: minioBucket, secure: minioSecure,
        },
      })
      setInfraSaved(true)
      toast.success("基础设施配置已保存")
    } catch {
      toast.error("保存失败")
    } finally {
      setSavingInfra(false)
    }
  }

  function handleTypeChange(val: string) {
    setType(val)
    const def = PROVIDER_TYPES.find((t) => t.value === val)
    if (def && "defaultUrl" in def && def.defaultUrl) setBaseUrl(def.defaultUrl)
    setModels([])
    setTestOk(null)
  }

  async function handleDiscover() {
    setDiscovering(true)
    try {
      const res = await modelApi.discover({
        type,
        base_url: baseUrl || undefined,
        api_key: apiKey || undefined,
      })
      const discovered: DiscoveredModel[] = res.models.map((m) => ({
        id: m.id,
        category: (m.type_hint === "embedding" ? "embedding" : m.type_hint === "reranker" ? "reranker" : "llm") as DiscoveredModel["category"],
        checked: true,
      }))
      setModels(discovered)
      toast.success(`发现 ${discovered.length} 个模型`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "模型发现失败")
    } finally {
      setDiscovering(false)
    }
  }

  function toggleModel(idx: number) {
    setModels((prev) => prev.map((m, i) => (i === idx ? { ...m, checked: !m.checked } : m)))
  }

  function reclassify(idx: number, cat: DiscoveredModel["category"]) {
    setModels((prev) => prev.map((m, i) => (i === idx ? { ...m, category: cat } : m)))
  }

  async function handleSaveAndTest() {
    if (!name || !type) return
    setSaving(true)
    setTesting(true)
    setTestOk(null)
    try {
      const checked = models.filter((m) => m.checked)
      const provider = await modelApi.create({
        name,
        type,
        base_url: baseUrl || undefined,
        api_key: apiKey || undefined,
        models_available: {
          llm: checked.filter((m) => m.category === "llm").map((m) => m.id),
          embedding: checked.filter((m) => m.category === "embedding").map((m) => m.id),
          reranker: checked.filter((m) => m.category === "reranker").map((m) => m.id),
        },
      })
      const result = await modelApi.test(provider.id)
      const ok = result.llm === "ok" || result.llm === "success"
      setTestOk(ok)
      setTestMsg(`LLM: ${result.llm}${result.embedding ? ` | Embedding: ${result.embedding}` : ""}`)
      if (ok) toast.success("连接测试成功")
      else toast.warning("部分能力测试未通过")
    } catch (err) {
      setTestOk(false)
      setTestMsg(err instanceof Error ? err.message : "创建或测试失败")
      toast.error("操作失败")
    } finally {
      setSaving(false)
      setTesting(false)
    }
  }

  const catLabel: Record<string, string> = { llm: "LLM", embedding: "Embedding", reranker: "Reranker" }
  const categories: DiscoveredModel["category"][] = ["llm", "embedding", "reranker"]

  function TestBadge({ status, detail }: { status: TestStatus; detail?: string }) {
    if (status === "idle") return null
    if (status === "testing") return <Loader2 className="size-4 animate-spin text-muted-foreground" />
    return (
      <span className="flex items-center gap-1 text-xs">
        {status === "ok"
          ? <CheckCircle2 className="size-3.5 text-green-500" />
          : <XCircle className="size-3.5 text-red-500" />}
        {status === "ok" ? "连接成功" : detail || "连接失败"}
      </span>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Milvus */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Database className="size-4" />
            <CardTitle>配置 Milvus</CardTitle>
          </div>
          <CardDescription>向量数据库，用于知识库检索</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div>
            <Label>URI</Label>
            <Input value={milvusUri} onChange={(e) => setMilvusUri(e.target.value)} placeholder="http://localhost:19530" />
          </div>
          <div>
            <Label>Token (可选)</Label>
            <Input type="password" value={milvusToken} onChange={(e) => setMilvusToken(e.target.value)} placeholder="留空表示无认证" />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleTestMilvus} disabled={milvusTest === "testing"}>
              {milvusTest === "testing" ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : null}
              测试连接
            </Button>
            <TestBadge status={milvusTest} detail={milvusDetail} />
          </div>
        </CardContent>
      </Card>

      {/* MinIO */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <HardDrive className="size-4" />
            <CardTitle>配置 MinIO</CardTitle>
          </div>
          <CardDescription>对象存储，用于文档文件存储</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div>
            <Label>Endpoint</Label>
            <Input value={minioEndpoint} onChange={(e) => setMinioEndpoint(e.target.value)} placeholder="localhost:9000" />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label>Access Key</Label>
              <Input value={minioAccessKey} onChange={(e) => setMinioAccessKey(e.target.value)} />
            </div>
            <div>
              <Label>Secret Key</Label>
              <Input type="password" value={minioSecretKey} onChange={(e) => setMinioSecretKey(e.target.value)} />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label>Bucket</Label>
              <Input value={minioBucket} onChange={(e) => setMinioBucket(e.target.value)} />
            </div>
            <div className="flex items-center gap-2 pt-6">
              <Switch checked={minioSecure} onCheckedChange={setMinioSecure} />
              <Label className="text-sm">HTTPS</Label>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleTestMinio} disabled={minioTest === "testing"}>
              {minioTest === "testing" ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : null}
              测试连接
            </Button>
            <TestBadge status={minioTest} detail={minioDetail} />
          </div>
        </CardContent>
      </Card>

      {/* Save infra button */}
      {(milvusTest === "ok" || minioTest === "ok") && !infraSaved && (
        <Button variant="outline" onClick={handleSaveInfra} disabled={savingInfra}>
          {savingInfra ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : null}
          保存基础设施配置
        </Button>
      )}
      {infraSaved && (
        <div className="flex items-center gap-1.5 text-sm text-green-600">
          <CheckCircle2 className="size-4" />
          基础设施配置已保存
        </div>
      )}

      <Separator />

      {/* LLM Provider */}
      <Card>
        <CardHeader>
          <CardTitle>配置 AI 模型</CardTitle>
          <CardDescription>添加至少一个 LLM 和 Embedding 模型提供商</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {/* Credentials */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label>名称</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. OpenAI" />
            </div>
            <div>
              <Label>类型</Label>
              <Select value={type || undefined} onValueChange={(v) => v && handleTypeChange(v)}>
                <SelectTrigger className="w-full">
                  {type
                    ? <span>{PROVIDER_TYPES.find((t) => t.value === type)?.label ?? type}</span>
                    : <SelectValue placeholder="选择供应商类型" />}
                </SelectTrigger>
                <SelectContent>
                  {PROVIDER_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {type && (typeDef?.needsUrl !== false || baseUrl) && (
            <div>
              <Label>API Base URL</Label>
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={typeDef?.defaultUrl ?? "https://..."}
              />
            </div>
          )}

          {type && typeDef?.needsKey !== false && (
            <div>
              <Label>API Key</Label>
              <Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." />
            </div>
          )}

          {/* Model Discovery */}
          {type && (
            <>
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">模型列表</Label>
                <Button
                  variant="outline" size="sm"
                  onClick={handleDiscover}
                  disabled={!type || discovering}
                >
                  {discovering
                    ? <Loader2 className="mr-1 size-3.5 animate-spin" />
                    : <Search className="mr-1 size-3.5" />}
                  {discovering ? "发现中..." : "发现模型"}
                </Button>
              </div>

              {models.length > 0 && (
                <div className="grid gap-3 sm:grid-cols-3">
                  {categories.map((cat) => {
                    const items = models
                      .map((m, i) => ({ ...m, _idx: i }))
                      .filter((m) => m.category === cat)
                    return (
                      <div key={cat}>
                        <p className="mb-1.5 text-xs font-semibold text-muted-foreground">{catLabel[cat]}</p>
                        <div className="space-y-1">
                          {items.map((m) => (
                            <div key={m._idx} className="flex items-center gap-2 rounded border px-2 py-1 text-xs">
                              <Switch
                                checked={m.checked}
                                onCheckedChange={() => toggleModel(m._idx)}
                                className="scale-75"
                              />
                              <span className="flex-1 truncate" title={m.id}>{m.id}</span>
                              <Select
                                value={m.category}
                                onValueChange={(v) => reclassify(m._idx, v as DiscoveredModel["category"])}
                              >
                                <SelectTrigger className="h-6 w-20 text-[10px]">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="llm">LLM</SelectItem>
                                  <SelectItem value="embedding">Embedding</SelectItem>
                                  <SelectItem value="reranker">Reranker</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                          ))}
                          {items.length === 0 && <p className="text-xs text-muted-foreground">-</p>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}

          {/* Test result */}
          {testOk !== null && (
            <div className="flex items-center gap-1.5 text-sm">
              {testOk
                ? <CheckCircle2 className="size-4 text-green-500" />
                : <XCircle className="size-4 text-red-500" />}
              <span>{testMsg}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2">
            {onBack && <Button variant="outline" onClick={onBack}>上一步</Button>}
            <Button
              variant="outline"
              onClick={handleSaveAndTest}
              disabled={!name || !type || saving || testing}
            >
              {saving || testing ? "处理中..." : "添加并测试连接"}
            </Button>
            <Button onClick={() => (testOk === true || !name) ? onNext() : toast.info("请先完成配置并通过测试")} className="flex-1">
              {name ? "下一步" : "跳过"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
