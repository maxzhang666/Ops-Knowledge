import { useCallback, useEffect, useState } from "react"
import { Plus, Save, Trash2, KeyRound } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import { systemApi } from "@/api/system"

const KNOWN_ROLES = ["system_admin", "user"]

// SSO settings shape matches backend app.system.schemas.SsoSettings.
interface SsoSettings {
  enabled: boolean
  issuer: string
  client_id: string
  client_secret: string  // write-only — loaded as "" so we don't leak the stored value
  redirect_uri: string
  scopes: string
  group_claim: string
  role_map: Record<string, string>
  dept_map: Record<string, string>
  button_label: string
}

const DEFAULTS: SsoSettings = {
  enabled: false,
  issuer: "",
  client_id: "",
  client_secret: "",
  redirect_uri: `${window.location.origin}/api/v1/auth/sso/callback`,
  scopes: "openid profile email",
  group_claim: "groups",
  role_map: {},
  dept_map: {},
  button_label: "使用 SSO 登录",
}


export function SsoConfigCard() {
  const [cfg, setCfg] = useState<SsoSettings>(structuredClone(DEFAULTS))
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [hasStoredSecret, setHasStoredSecret] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const all = await systemApi.getSettings()
      const saved = (all?.sso ?? {}) as Partial<SsoSettings>
      // Stored secret detection — never echo the value itself back into the
      // input. We only track "is one set" to show the placeholder.
      setHasStoredSecret(Boolean(saved.client_secret))
      setCfg({
        ...DEFAULTS,
        ...saved,
        client_secret: "",
        role_map: (saved.role_map ?? {}) as Record<string, string>,
        dept_map: (saved.dept_map ?? {}) as Record<string, string>,
        // Always use runtime origin for redirect_uri display — prevents stale
        // stored values from confusing the admin during migrations.
        redirect_uri: saved.redirect_uri || DEFAULTS.redirect_uri,
      })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function validate(): string | null {
    if (!cfg.enabled) return null
    if (!cfg.issuer.trim()) return "Issuer URL 为必填"
    if (!cfg.client_id.trim()) return "Client ID 为必填"
    if (!cfg.redirect_uri.trim()) return "Redirect URI 为必填"
    if (!cfg.scopes.split(/\s+/).includes("openid")) return "Scopes 必须包含 openid"
    for (const [g, r] of Object.entries(cfg.role_map)) {
      if (!g.trim()) return "角色映射 key 不能为空"
      if (!KNOWN_ROLES.includes(r)) return `角色映射值必须是 ${KNOWN_ROLES.join(" / ")}`
    }
    return null
  }

  async function handleSave() {
    const err = validate()
    if (err) { toast.error(err); return }
    setSaving(true)
    try {
      const payload: Partial<SsoSettings> = { ...cfg }
      // Empty client_secret means "leave existing untouched" — drop the key
      // so backend's merge semantics don't overwrite with empty string.
      if (!cfg.client_secret) delete payload.client_secret
      await systemApi.updateSettings({ sso: payload })
      toast.success("SSO 配置已保存")
      await load()
    } catch {
      toast.error("保存失败")
    } finally {
      setSaving(false)
    }
  }

  function update<K extends keyof SsoSettings>(key: K, value: SsoSettings[K]) {
    setCfg((prev) => ({ ...prev, [key]: value }))
  }

  function updateMapEntry(
    mapKey: "role_map" | "dept_map", oldKey: string, newKey: string, value: string,
  ) {
    setCfg((prev) => {
      const next = { ...prev[mapKey] }
      if (oldKey && oldKey !== newKey) delete next[oldKey]
      if (newKey) next[newKey] = value
      return { ...prev, [mapKey]: next }
    })
  }

  function removeMapEntry(mapKey: "role_map" | "dept_map", key: string) {
    setCfg((prev) => {
      const next = { ...prev[mapKey] }
      delete next[key]
      return { ...prev, [mapKey]: next }
    })
  }

  function addMapEntry(mapKey: "role_map" | "dept_map") {
    setCfg((prev) => {
      const next = { ...prev[mapKey], "": "" }
      return { ...prev, [mapKey]: next }
    })
  }

  if (loading) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="size-4" /> SSO 认证
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Switch checked={cfg.enabled} onCheckedChange={(v) => update("enabled", v)} />
          <Label className="text-sm">启用 SSO</Label>
        </div>

        {cfg.enabled && (
          <>
            <Separator />
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <Label className="text-xs">Issuer URL</Label>
                <Input
                  value={cfg.issuer}
                  onChange={(e) => update("issuer", e.target.value)}
                  placeholder="https://keycloak.example.com/realms/main"
                />
              </div>
              <div>
                <Label className="text-xs">Client ID</Label>
                <Input
                  value={cfg.client_id}
                  onChange={(e) => update("client_id", e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs">
                  Client Secret {hasStoredSecret && (
                    <span className="ml-1 text-muted-foreground">（已保存，留空不修改）</span>
                  )}
                </Label>
                <Input
                  type="password"
                  value={cfg.client_secret}
                  onChange={(e) => update("client_secret", e.target.value)}
                  placeholder={hasStoredSecret ? "••••••••" : ""}
                />
              </div>
              <div>
                <Label className="text-xs">Redirect URI</Label>
                <Input value={cfg.redirect_uri} readOnly className="font-mono text-xs" />
              </div>
              <div>
                <Label className="text-xs">Scopes</Label>
                <Input
                  value={cfg.scopes}
                  onChange={(e) => update("scopes", e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs">Group Claim 字段</Label>
                <Input
                  value={cfg.group_claim}
                  onChange={(e) => update("group_claim", e.target.value)}
                />
              </div>
              <div className="md:col-span-2">
                <Label className="text-xs">登录按钮文案</Label>
                <Input
                  value={cfg.button_label}
                  onChange={(e) => update("button_label", e.target.value)}
                />
              </div>
            </div>

            <Separator />
            <MapEditor
              title="角色映射"
              hint={`IdP 组 → 平台角色（${KNOWN_ROLES.join(" / ")}）`}
              entries={cfg.role_map}
              valueOptions={KNOWN_ROLES}
              onChange={(oldKey, newKey, value) => updateMapEntry("role_map", oldKey, newKey, value)}
              onRemove={(k) => removeMapEntry("role_map", k)}
              onAdd={() => addMapEntry("role_map")}
            />

            <Separator />
            <MapEditor
              title="部门映射"
              hint="IdP 组 → 部门名称（不存在则自动创建）"
              entries={cfg.dept_map}
              onChange={(oldKey, newKey, value) => updateMapEntry("dept_map", oldKey, newKey, value)}
              onRemove={(k) => removeMapEntry("dept_map", k)}
              onAdd={() => addMapEntry("dept_map")}
            />
          </>
        )}

        <div className="flex justify-end pt-2">
          <Button size="sm" onClick={handleSave} disabled={saving}>
            <Save className="mr-1 size-3.5" />
            {saving ? "保存中..." : "保存"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}


interface MapEditorProps {
  title: string
  hint: string
  entries: Record<string, string>
  valueOptions?: string[]
  onChange: (oldKey: string, newKey: string, value: string) => void
  onRemove: (key: string) => void
  onAdd: () => void
}

function MapEditor({ title, hint, entries, valueOptions, onChange, onRemove, onAdd }: MapEditorProps) {
  const rows = Object.entries(entries)
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-sm font-medium">{title}</div>
          <div className="text-xs text-muted-foreground">{hint}</div>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onAdd}>
          <Plus className="mr-1 size-3.5" /> 添加
        </Button>
      </div>
      {rows.length === 0 && (
        <p className="text-xs text-muted-foreground">暂无映射</p>
      )}
      <div className="space-y-2">
        {rows.map(([k, v], idx) => (
          <div key={`${idx}-${k}`} className="flex gap-2">
            <Input
              placeholder="IdP 组名"
              value={k}
              onChange={(e) => onChange(k, e.target.value, v)}
              className="flex-1"
            />
            {valueOptions ? (
              <select
                value={v}
                onChange={(e) => onChange(k, k, e.target.value)}
                className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="">选择</option>
                {valueOptions.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : (
              <Input
                placeholder="映射值"
                value={v}
                onChange={(e) => onChange(k, k, e.target.value)}
                className="flex-1"
              />
            )}
            <Button
              type="button" variant="ghost" size="icon"
              onClick={() => onRemove(k)}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}
