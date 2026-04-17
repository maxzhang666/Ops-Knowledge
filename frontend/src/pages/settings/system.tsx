import { useCallback, useEffect, useState } from "react"
import {
  RefreshCw, Loader2, CheckCircle2, XCircle, Save,
  Database, HardDrive, Upload, Shield, Gauge,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { systemApi, type HealthResponse } from "@/api/system"

const svcStatusColor: Record<string, string> = {
  ok: "bg-green-500",
  unavailable: "bg-red-500",
}

const svcStatusLabel: Record<string, string> = {
  ok: "正常",
  unavailable: "不可用",
}

type TestStatus = "idle" | "testing" | "ok" | "fail"

interface InfraConfig {
  milvus: { uri: string; token: string; timeout: number }
  minio: { endpoint: string; access_key: string; secret_key: string; bucket: string; secure: boolean }
  upload_limits: { max_file_size_mb: number; allowed_types: string }
  quotas: { max_kbs_per_user: number; max_docs_per_kb: number; max_storage_per_kb_mb: number }
  rate_limiting: { enabled: boolean; requests_per_minute: number }
}

const DEFAULTS: InfraConfig = {
  milvus: { uri: "http://localhost:19530", token: "", timeout: 30 },
  minio: { endpoint: "localhost:9000", access_key: "minioadmin", secret_key: "minioadmin", bucket: "ops-knowledge-docs", secure: false },
  upload_limits: { max_file_size_mb: 50, allowed_types: ".pdf,.md,.docx,.doc,.html,.txt,.csv,.pptx,.xlsx" },
  quotas: { max_kbs_per_user: 20, max_docs_per_kb: 500, max_storage_per_kb_mb: 2048 },
  rate_limiting: { enabled: true, requests_per_minute: 60 },
}

function deepMerge(defaults: InfraConfig, saved: Record<string, unknown>): InfraConfig {
  const result = structuredClone(defaults)
  for (const section of Object.keys(defaults) as (keyof InfraConfig)[]) {
    const sv = saved[section]
    if (sv && typeof sv === "object") {
      Object.assign(result[section], sv)
    }
  }
  return result
}

export default function SystemPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loadingHealth, setLoadingHealth] = useState(true)
  const [cfg, setCfg] = useState<InfraConfig>(structuredClone(DEFAULTS))
  const [savedSections, setSavedSections] = useState<Set<string>>(new Set())
  const [loadingCfg, setLoadingCfg] = useState(true)
  const [saving, setSaving] = useState(false)
  const [milvusTest, setMilvusTest] = useState<TestStatus>("idle")
  const [minioTest, setMinioTest] = useState<TestStatus>("idle")
  const [testDetail, setTestDetail] = useState<Record<string, string>>({})

  const loadHealth = useCallback(async () => {
    setLoadingHealth(true)
    try {
      setHealth(await systemApi.health())
    } finally {
      setLoadingHealth(false)
    }
  }, [])

  const loadConfig = useCallback(async () => {
    setLoadingCfg(true)
    try {
      const raw = await systemApi.getSettings()
      setCfg(deepMerge(DEFAULTS, raw))
      setSavedSections(new Set(Object.keys(raw).filter((k) => raw[k] && typeof raw[k] === "object" && Object.keys(raw[k] as object).length > 0)))
    } finally {
      setLoadingCfg(false)
    }
  }, [])

  useEffect(() => { loadHealth(); loadConfig() }, [loadHealth, loadConfig])

  function update<S extends keyof InfraConfig>(section: S, key: keyof InfraConfig[S], value: unknown) {
    setCfg((prev) => ({
      ...prev,
      [section]: { ...prev[section], [key]: value },
    }))
  }

  async function handleSave() {
    setSaving(true)
    try {
      await systemApi.updateSettings(cfg as unknown as Record<string, unknown>)
      setSavedSections(new Set(Object.keys(cfg)))
      toast.success("配置已保存")
    } catch {
      toast.error("保存失败")
    } finally {
      setSaving(false)
    }
  }

  async function testConnection(service: "milvus" | "minio") {
    const setter = service === "milvus" ? setMilvusTest : setMinioTest
    setter("testing")
    setTestDetail((p) => ({ ...p, [service]: "" }))
    try {
      const res = await systemApi.testConnection(service, cfg[service] as unknown as Record<string, unknown>)
      setter(res.ok ? "ok" : "fail")
      if (!res.ok) setTestDetail((p) => ({ ...p, [service]: res.detail || "Connection failed" }))
    } catch (e) {
      setter("fail")
      setTestDetail((p) => ({ ...p, [service]: e instanceof Error ? e.message : "Unknown error" }))
    }
  }

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

  if (loadingHealth && loadingCfg) return <LoadingSpinner className="py-16" />

  return (
    <div className="space-y-6">
      {/* Health Status */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">系统状态</h2>
          <div className="flex items-center gap-3">
            {health && (
              <span className="text-xs text-muted-foreground">版本: {health.version}</span>
            )}
            <Button variant="outline" size="sm" onClick={loadHealth} disabled={loadingHealth}>
              <RefreshCw className={`mr-1 size-3.5 ${loadingHealth ? "animate-spin" : ""}`} />
              刷新
            </Button>
          </div>
        </div>
        {health && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {Object.entries(health.services).map(([name, status]) => (
              <Card key={name} className="p-3">
                <div className="flex items-center gap-2">
                  <span className={`inline-block h-2 w-2 rounded-full ${svcStatusColor[status] ?? "bg-gray-400"}`} />
                  <span className="text-sm font-medium capitalize">{name}</span>
                  <Badge variant={status === "ok" ? "default" : "destructive"} className="ml-auto text-[10px]">
                    {svcStatusLabel[status] ?? status}
                  </Badge>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Separator />

      {/* Infrastructure Config */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">基础设施配置</h2>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : <Save className="mr-1 size-3.5" />}
            保存配置
          </Button>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          {/* Milvus */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Database className="size-4" />
                <CardTitle className="flex items-center gap-2 text-base">
                  Milvus 向量数据库
                  {!savedSections.has("milvus") && <Badge variant="outline" className="text-[10px] text-muted-foreground">使用环境变量默认值</Badge>}
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label>URI</Label>
                <Input value={cfg.milvus.uri} onChange={(e) => update("milvus", "uri", e.target.value)} placeholder="http://localhost:19530" />
              </div>
              <div>
                <Label>Token</Label>
                <Input type="password" value={cfg.milvus.token} onChange={(e) => update("milvus", "token", e.target.value)} placeholder="留空表示无认证" />
              </div>
              <div>
                <Label>超时 (秒)</Label>
                <Input type="number" value={cfg.milvus.timeout} onChange={(e) => update("milvus", "timeout", Number(e.target.value))} />
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => testConnection("milvus")} disabled={milvusTest === "testing"}>
                  {milvusTest === "testing" ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : null}
                  测试连接
                </Button>
                <TestBadge status={milvusTest} detail={testDetail.milvus} />
              </div>
            </CardContent>
          </Card>

          {/* MinIO */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <HardDrive className="size-4" />
                <CardTitle className="flex items-center gap-2 text-base">
                  MinIO 对象存储
                  {!savedSections.has("minio") && <Badge variant="outline" className="text-[10px] text-muted-foreground">使用环境变量默认值</Badge>}
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label>Endpoint</Label>
                <Input value={cfg.minio.endpoint} onChange={(e) => update("minio", "endpoint", e.target.value)} placeholder="localhost:9000" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>Access Key</Label>
                  <Input value={cfg.minio.access_key} onChange={(e) => update("minio", "access_key", e.target.value)} />
                </div>
                <div>
                  <Label>Secret Key</Label>
                  <Input type="password" value={cfg.minio.secret_key} onChange={(e) => update("minio", "secret_key", e.target.value)} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>Bucket</Label>
                  <Input value={cfg.minio.bucket} onChange={(e) => update("minio", "bucket", e.target.value)} />
                </div>
                <div className="flex items-center gap-2 pt-6">
                  <Switch checked={cfg.minio.secure} onCheckedChange={(v) => update("minio", "secure", v)} />
                  <Label className="text-sm">HTTPS</Label>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => testConnection("minio")} disabled={minioTest === "testing"}>
                  {minioTest === "testing" ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : null}
                  测试连接
                </Button>
                <TestBadge status={minioTest} detail={testDetail.minio} />
              </div>
            </CardContent>
          </Card>

          {/* Upload Limits */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Upload className="size-4" />
                <CardTitle className="text-base">上传限制</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label>最大文件大小 (MB)</Label>
                <Input type="number" value={cfg.upload_limits.max_file_size_mb} onChange={(e) => update("upload_limits", "max_file_size_mb", Number(e.target.value))} />
              </div>
              <div>
                <Label>允许的文件类型</Label>
                <Input value={cfg.upload_limits.allowed_types} onChange={(e) => update("upload_limits", "allowed_types", e.target.value)} placeholder=".pdf,.md,.docx,..." />
              </div>
            </CardContent>
          </Card>

          {/* Quotas */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Shield className="size-4" />
                <CardTitle className="text-base">配额</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label>每用户最大知识库数</Label>
                <Input type="number" value={cfg.quotas.max_kbs_per_user} onChange={(e) => update("quotas", "max_kbs_per_user", Number(e.target.value))} />
              </div>
              <div>
                <Label>每知识库最大文档数</Label>
                <Input type="number" value={cfg.quotas.max_docs_per_kb} onChange={(e) => update("quotas", "max_docs_per_kb", Number(e.target.value))} />
              </div>
              <div>
                <Label>每知识库最大存储 (MB)</Label>
                <Input type="number" value={cfg.quotas.max_storage_per_kb_mb} onChange={(e) => update("quotas", "max_storage_per_kb_mb", Number(e.target.value))} />
              </div>
            </CardContent>
          </Card>

          {/* Rate Limiting */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Gauge className="size-4" />
                <CardTitle className="text-base">速率限制</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <Switch checked={cfg.rate_limiting.enabled} onCheckedChange={(v) => update("rate_limiting", "enabled", v)} />
                <Label className="text-sm">启用速率限制</Label>
              </div>
              {cfg.rate_limiting.enabled && (
                <div>
                  <Label>每分钟请求数</Label>
                  <Input type="number" value={cfg.rate_limiting.requests_per_minute} onChange={(e) => update("rate_limiting", "requests_per_minute", Number(e.target.value))} />
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
