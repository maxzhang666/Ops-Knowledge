import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Plus, Trash2, Pencil, PlayCircle, RefreshCw, CheckCircle2, XCircle, Loader2, Wrench, Plug,
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
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import {
  mcpApi, type MCPServer, type MCPTool, type MCPTransportType,
} from "@/api/mcp"

// Transport options — labels + per-transport placeholder hints for the
// form. Keep this data-driven so adding a new transport is a one-line change.
const TRANSPORTS: Array<{
  value: MCPTransportType
  label: string
  hint: string
  recommended?: boolean
  legacy?: boolean
}> = [
  { value: "http", label: "Streamable HTTP", hint: "https://.../mcp", recommended: true },
  { value: "sse", label: "SSE (legacy)", hint: "https://.../sse", legacy: true },
  { value: "stdio", label: "stdio", hint: "command + args" },
]

const HEALTH_VARIANT: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  ok: { label: "健康", variant: "default" },
  degraded: { label: "降级", variant: "secondary" },
  unreachable: { label: "不可达", variant: "destructive" },
}

type ToolCacheEntry = { loading: boolean; tools: MCPTool[] | null; error?: string }

export default function McpServersPage() {
  const [servers, setServers] = useState<MCPServer[]>([])
  const [loading, setLoading] = useState(true)

  // Dialog (create / edit)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<MCPServer | null>(null)
  const [form, setForm] = useState(blankForm())
  const [saving, setSaving] = useState(false)

  // Per-server side state
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; msg: string }>>({})
  const [toolsCache, setToolsCache] = useState<Record<string, ToolCacheEntry>>({})
  const [toolsDrawerId, setToolsDrawerId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const rows = await mcpApi.list()
      setServers(Array.isArray(rows) ? rows : [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function openCreate() {
    setEditing(null)
    setForm(blankForm())
    setDialogOpen(true)
  }

  function openEdit(s: MCPServer) {
    setEditing(s)
    setForm({
      name: s.name,
      description: s.description ?? "",
      transport_type: s.transport_type as MCPTransportType,
      url: (s.config?.url as string) ?? "",
      headers_raw: stringifyKv(s.config?.headers as Record<string, string> | undefined),
      command: (s.config?.command as string) ?? "",
      args_raw: ((s.config?.args as string[]) ?? []).join(" "),
      env_raw: stringifyKv(s.config?.env as Record<string, string> | undefined),
      bearer_token: (s.auth_config?.bearer_token as string) ?? "",
      is_active: s.is_active,
    })
    setDialogOpen(true)
  }

  async function handleSave() {
    setSaving(true)
    try {
      const payload = serializeForm(form)
      if (editing) {
        await mcpApi.update(editing.id, payload)
        toast.success("已更新")
      } else {
        await mcpApi.create(payload)
        toast.success("已创建")
      }
      setDialogOpen(false)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await mcpApi.delete(deleteTarget)
      toast.success("已删除")
      setServers((prev) => prev.filter((s) => s.id !== deleteTarget))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  async function handleTest(id: string) {
    setTestingId(id)
    try {
      const r = await mcpApi.testConnection(id)
      setTestResults((prev) => ({
        ...prev,
        [id]: {
          ok: r.ok,
          msg: r.ok
            ? `${r.server_info?.name ?? "handshake"} / ${r.server_info?.protocol_version ?? "unknown"}`
            : r.detail,
        },
      }))
      // Reload so health_status badge updates
      load()
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [id]: { ok: false, msg: err instanceof Error ? err.message : "测试失败" },
      }))
    } finally {
      setTestingId(null)
    }
  }

  async function handleDiscover(id: string) {
    setToolsCache((prev) => ({ ...prev, [id]: { loading: true, tools: prev[id]?.tools ?? null } }))
    try {
      const tools = await mcpApi.discoverTools(id)
      setToolsCache((prev) => ({ ...prev, [id]: { loading: false, tools } }))
      toast.success(`发现 ${tools.length} 个工具`)
      load()
    } catch (err) {
      const msg = err instanceof Error ? err.message : "发现失败"
      setToolsCache((prev) => ({ ...prev, [id]: { loading: false, tools: null, error: msg } }))
      toast.error(msg)
    }
  }

  function openToolsDrawer(id: string) {
    setToolsDrawerId(id)
    // Lazy-load on first open
    if (!toolsCache[id]?.tools) handleDiscover(id)
  }

  async function handleToggleTool(id: string, toolName: string, checked: boolean) {
    const server = servers.find((s) => s.id === id)
    if (!server) return
    const current = server.enabled_tools
    // null = all; transition to explicit list on first edit
    const base = current == null
      ? (toolsCache[id]?.tools ?? []).map((t) => t.name)
      : [...current]
    const next = checked ? Array.from(new Set([...base, toolName])) : base.filter((n) => n !== toolName)
    try {
      const updated = await mcpApi.update(id, { enabled_tools: next })
      setServers((prev) => prev.map((s) => (s.id === id ? updated : s)))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新失败")
    }
  }

  const drawerServer = useMemo(
    () => servers.find((s) => s.id === toolsDrawerId),
    [servers, toolsDrawerId],
  )

  if (loading) return <LoadingSpinner className="py-16" />

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">MCP 服务器</h2>
          <p className="text-xs text-muted-foreground">系统级资源，配置后可被智能体选用</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="mr-1 size-4" /> 添加服务器
        </Button>
      </div>

      {servers.length === 0 ? (
        <div className="rounded-lg border p-10 text-center text-sm text-muted-foreground">
          <Plug className="mx-auto mb-2 size-8 opacity-50" />
          暂无 MCP 服务器，点击右上角"添加服务器"开始
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {servers.map((s) => {
            const health = s.health_status ? HEALTH_VARIANT[s.health_status] : null
            const toolCount = s.discovered_tools?.length ?? 0
            return (
              <Card key={s.id} size="sm">
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <CardTitle className="flex-1 truncate text-base">{s.name}</CardTitle>
                    <Badge variant="secondary" className="text-[10px]">{s.transport_type}</Badge>
                    {health && <Badge variant={health.variant} className="text-[10px]">{health.label}</Badge>}
                  </div>
                  {s.description && (
                    <p className="text-xs text-muted-foreground line-clamp-2">{s.description}</p>
                  )}
                </CardHeader>
                <CardContent>
                  <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
                    <Wrench className="size-3.5" />
                    <span>{toolCount} 个工具{s.enabled_tools == null ? "" : `，已启用 ${s.enabled_tools.length}`}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-1">
                    <Button variant="ghost" size="sm" onClick={() => openEdit(s)}>
                      <Pencil className="mr-1 size-3.5" /> 编辑
                    </Button>
                    <Button
                      variant="ghost" size="sm"
                      onClick={() => handleTest(s.id)}
                      disabled={testingId === s.id}
                    >
                      {testingId === s.id
                        ? <Loader2 className="mr-1 size-3.5 animate-spin" />
                        : <PlayCircle className="mr-1 size-3.5" />}
                      测试
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => openToolsDrawer(s.id)}>
                      <Wrench className="mr-1 size-3.5" /> 工具
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(s.id)}>
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                  {testResults[s.id] && (
                    <div className="mt-2 flex items-start gap-1.5 text-xs">
                      {testResults[s.id].ok
                        ? <CheckCircle2 className="size-3.5 shrink-0 text-green-500" />
                        : <XCircle className="size-3.5 shrink-0 text-red-500" />}
                      <span className="break-all">{testResults[s.id].msg}</span>
                    </div>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* Create / Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(v) => { if (!v) setDialogOpen(false) }}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{editing ? "编辑 MCP 服务器" : "添加 MCP 服务器"}</DialogTitle>
            <DialogDescription>
              {editing ? "修改服务器配置" : "配置一个 MCP 服务器，可被智能体选用"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex max-h-[65vh] flex-col gap-4 overflow-y-auto pr-1">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label>名称</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="flex flex-col gap-2">
                <Label>传输类型</Label>
                <Select
                  value={form.transport_type}
                  onValueChange={(v) => v && setForm({ ...form, transport_type: v as MCPTransportType })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TRANSPORTS.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                        {t.recommended && <span className="ml-1 text-[10px] text-primary">推荐</span>}
                        {t.legacy && <span className="ml-1 text-[10px] text-muted-foreground">已弃用</span>}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <Label>描述</Label>
              <Textarea
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={2}
                placeholder="简要说明用途（可选）"
              />
            </div>

            {/* Transport-specific fields */}
            {form.transport_type !== "stdio" ? (
              <>
                <div className="flex flex-col gap-2">
                  <Label>URL</Label>
                  <Input
                    value={form.url}
                    onChange={(e) => setForm({ ...form, url: e.target.value })}
                    placeholder={TRANSPORTS.find((t) => t.value === form.transport_type)?.hint}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label>自定义请求头（每行 key=value，可选）</Label>
                  <Textarea
                    value={form.headers_raw}
                    onChange={(e) => setForm({ ...form, headers_raw: e.target.value })}
                    rows={2}
                    placeholder="X-Tenant=acme"
                    className="font-mono text-xs"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label>Bearer Token（可选）</Label>
                  <Input
                    type="password"
                    value={form.bearer_token}
                    onChange={(e) => setForm({ ...form, bearer_token: e.target.value })}
                    placeholder="sk-..."
                  />
                </div>
              </>
            ) : (
              <>
                <div className="flex flex-col gap-2">
                  <Label>Command</Label>
                  <Input
                    value={form.command}
                    onChange={(e) => setForm({ ...form, command: e.target.value })}
                    placeholder="npx"
                    className="font-mono text-xs"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label>Args（空格分隔）</Label>
                  <Input
                    value={form.args_raw}
                    onChange={(e) => setForm({ ...form, args_raw: e.target.value })}
                    placeholder="-y @modelcontextprotocol/server-everything"
                    className="font-mono text-xs"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label>环境变量（每行 key=value，可选）</Label>
                  <Textarea
                    value={form.env_raw}
                    onChange={(e) => setForm({ ...form, env_raw: e.target.value })}
                    rows={2}
                    placeholder="API_KEY=xxx"
                    className="font-mono text-xs"
                  />
                </div>
              </>
            )}

            <div className="flex items-center gap-2">
              <Switch
                checked={form.is_active}
                onCheckedChange={(v) => setForm({ ...form, is_active: v })}
              />
              <Label>激活</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>取消</Button>
            <Button onClick={handleSave} disabled={!form.name || saving}>
              {saving ? "保存中..." : "保存"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Tools drawer (dialog) */}
      <Dialog open={!!toolsDrawerId} onOpenChange={(v) => { if (!v) setToolsDrawerId(null) }}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>工具列表 {drawerServer && `— ${drawerServer.name}`}</DialogTitle>
            <DialogDescription>
              启用哪些工具对智能体可见；未勾选则隐藏
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-y-auto">
            {toolsDrawerId && (() => {
              const entry = toolsCache[toolsDrawerId]
              if (entry?.loading) return <LoadingSpinner className="py-8" />
              if (entry?.error) {
                return (
                  <div className="rounded border border-destructive/40 bg-destructive/5 p-3 text-xs">
                    <div className="mb-2 text-destructive">{entry.error}</div>
                    <Button variant="outline" size="sm" onClick={() => handleDiscover(toolsDrawerId)}>
                      <RefreshCw className="mr-1 size-3.5" /> 重试
                    </Button>
                  </div>
                )
              }
              const tools = entry?.tools ?? []
              if (tools.length === 0) {
                return <p className="p-4 text-center text-xs text-muted-foreground">该服务器无工具</p>
              }
              const enabled = drawerServer?.enabled_tools
              const isEnabled = (name: string) => enabled == null || enabled.includes(name)
              return (
                <div className="flex flex-col gap-1.5">
                  <div className="mb-1 flex items-center justify-between px-1 text-xs text-muted-foreground">
                    <span>共 {tools.length} 个工具</span>
                    <Button variant="ghost" size="sm" onClick={() => handleDiscover(toolsDrawerId)}>
                      <RefreshCw className="mr-1 size-3" /> 刷新
                    </Button>
                  </div>
                  {tools.map((t) => (
                    <label
                      key={t.name}
                      className="flex cursor-pointer items-start gap-3 rounded border px-3 py-2 hover:bg-muted/40"
                    >
                      <Switch
                        checked={isEnabled(t.name)}
                        onCheckedChange={(v) => handleToggleTool(toolsDrawerId, t.name, v)}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="font-mono text-xs font-medium">{t.name}</div>
                        {t.description && (
                          <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{t.description}</div>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              )
            })()}
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除 MCP 服务器"
        description="确认删除？已选中该服务器的智能体将无法调用其工具。"
        confirmText="删除"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}

// ─── Form helpers ────────────────────────────────────────────────

interface FormState {
  name: string
  description: string
  transport_type: MCPTransportType
  url: string
  headers_raw: string
  command: string
  args_raw: string
  env_raw: string
  bearer_token: string
  is_active: boolean
}

function blankForm(): FormState {
  return {
    name: "",
    description: "",
    transport_type: "http",
    url: "",
    headers_raw: "",
    command: "",
    args_raw: "",
    env_raw: "",
    bearer_token: "",
    is_active: true,
  }
}

function parseKv(raw: string): Record<string, string> | undefined {
  const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean)
  if (lines.length === 0) return undefined
  const out: Record<string, string> = {}
  for (const line of lines) {
    const idx = line.indexOf("=")
    if (idx <= 0) continue
    out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
  }
  return Object.keys(out).length > 0 ? out : undefined
}

function stringifyKv(obj?: Record<string, string>): string {
  if (!obj) return ""
  return Object.entries(obj).map(([k, v]) => `${k}=${v}`).join("\n")
}

function serializeForm(f: FormState) {
  const config: Record<string, unknown> = {}
  if (f.transport_type === "stdio") {
    config.command = f.command.trim()
    config.args = f.args_raw.trim() ? f.args_raw.trim().split(/\s+/) : []
    const env = parseKv(f.env_raw)
    if (env) config.env = env
  } else {
    config.url = f.url.trim()
    const headers = parseKv(f.headers_raw)
    if (headers) config.headers = headers
  }
  const payload: Record<string, unknown> = {
    name: f.name.trim(),
    description: f.description.trim() || null,
    transport_type: f.transport_type,
    config,
    is_active: f.is_active,
  }
  if (f.bearer_token.trim()) {
    payload.auth_config = { bearer_token: f.bearer_token.trim() }
  }
  return payload as never
}
