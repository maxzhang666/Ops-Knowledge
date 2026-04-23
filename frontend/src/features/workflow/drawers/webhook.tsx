import { useEffect, useMemo, useState } from "react"
import { Copy, Globe, RotateCw, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { workflowApi } from "@/api/workflow"
import { useEditorStore } from "../store"

type AuthType = "none" | "bearer" | "hmac"

interface WebhookCfg {
  hook_id?: string
  auth_type?: AuthType
  allowed_ips?: string[]
  secret?: string  // only present once after regenerate; never stored in state afterwards
}


export function WebhookDrawer() {
  const workflow = useEditorStore((s) => s.workflow)
  const setWorkflow = useEditorStore((s) => s.setWorkflow)
  const workflowId = workflow?.id
  const [open, setOpen] = useState(false)
  const [cfg, setCfg] = useState<WebhookCfg>({})
  const [newSecret, setNewSecret] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // 仅依赖 open + workflowId — 依赖整个 workflow 对象会形成 fetch→setWorkflow→
  // effect 重跑的无限循环（表现为抽屉闪烁）。setWorkflow 从 store 拿，stable。
  useEffect(() => {
    if (!open || !workflowId) return
    workflowApi.get(workflowId).then((wf) => {
      setWorkflow(wf)
      const c = wf.webhook_config ?? {}
      setCfg({
        hook_id: c.hook_id,
        auth_type: (c.auth_type as AuthType | undefined) ?? "none",
        allowed_ips: c.allowed_ips ?? [],
      })
      setNewSecret(null)
    })
  }, [open, workflowId, setWorkflow])

  const publicUrl = useMemo(() => {
    if (!cfg.hook_id) return ""
    return `${window.location.origin}/api/v1/webhook/${cfg.hook_id}`
  }, [cfg.hook_id])

  async function regenerate(auth_type: AuthType) {
    if (!workflow) return
    if (!window.confirm("重新生成会使旧 URL / 密钥立即失效。确定？")) return
    setSaving(true)
    try {
      const resp = await workflowApi.regenerateWebhook(workflow.id, auth_type)
      setCfg({
        hook_id: resp.hook_id,
        auth_type: resp.auth_type as AuthType,
        allowed_ips: resp.allowed_ips ?? [],
      })
      // Secret is surfaced ONCE — stored only in newSecret state, never echoed.
      if (resp.secret) setNewSecret(resp.secret)
      toast.success("已重新生成")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "生成失败")
    } finally {
      setSaving(false)
    }
  }

  async function saveConfig() {
    if (!workflow) return
    setSaving(true)
    try {
      await workflowApi.updateWebhookConfig(workflow.id, {
        auth_type: cfg.auth_type,
        allowed_ips: cfg.allowed_ips ?? [],
      })
      toast.success("配置已保存")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  async function removeWebhook() {
    if (!workflow) return
    if (!window.confirm("删除 Webhook 配置后外部触发将失效。确定？")) return
    try {
      await workflowApi.deleteWebhook(workflow.id)
      setCfg({})
      setNewSecret(null)
      toast.success("已删除 Webhook")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败")
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text)
      .then(() => toast.success("已复制"))
      .catch(() => toast.error("复制失败"))
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="outline" size="sm" />}>
        <Globe className="mr-1 size-3.5" /> Webhook
      </SheetTrigger>
      <SheetContent className="w-[28rem]">
        <SheetHeader>
          <SheetTitle>Webhook 配置</SheetTitle>
          <SheetDescription>
            外部系统通过此 URL 触发工作流执行
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 space-y-4 text-sm">
          {!cfg.hook_id ? (
            <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
              尚未生成 Webhook
              <div className="mt-2 flex justify-center gap-2">
                <Button size="sm" onClick={() => regenerate("hmac")} disabled={saving}>
                  生成（HMAC）
                </Button>
                <Button size="sm" variant="outline" onClick={() => regenerate("none")} disabled={saving}>
                  生成（无认证）
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div>
                <Label className="text-xs">公开 URL</Label>
                <div className="flex gap-1">
                  <Input value={publicUrl} readOnly className="font-mono text-xs" />
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-9 w-9"
                    onClick={() => copyToClipboard(publicUrl)}
                  >
                    <Copy className="size-3.5" />
                  </Button>
                </div>
              </div>

              <div>
                <Label className="text-xs">认证方式</Label>
                <select
                  value={cfg.auth_type ?? "none"}
                  onChange={(e) =>
                    setCfg((c) => ({ ...c, auth_type: e.target.value as AuthType }))
                  }
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="none">无认证（仅靠 IP 允许名单）</option>
                  <option value="bearer">Bearer Token</option>
                  <option value="hmac">HMAC SHA-256</option>
                </select>
              </div>

              <div>
                <Label className="text-xs">
                  允许的 IP（每行一个；留空放行所有）
                </Label>
                <Textarea
                  rows={3}
                  value={(cfg.allowed_ips ?? []).join("\n")}
                  onChange={(e) =>
                    setCfg((c) => ({
                      ...c,
                      allowed_ips: e.target.value.split("\n").filter(Boolean),
                    }))
                  }
                />
              </div>

              {newSecret && (
                <div className="rounded-md border border-yellow-300 bg-yellow-50 p-3 text-xs dark:border-yellow-700 dark:bg-yellow-950">
                  <div className="font-medium">密钥仅显示一次，请立即复制</div>
                  <div className="mt-1 flex items-center gap-1">
                    <Input value={newSecret} readOnly className="font-mono text-xs" />
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => copyToClipboard(newSecret)}
                    >
                      <Copy className="size-3.5" />
                    </Button>
                  </div>
                </div>
              )}

              <div className="flex flex-wrap gap-2 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => regenerate(cfg.auth_type ?? "hmac")}
                  disabled={saving}
                >
                  <RotateCw className="mr-1 size-3.5" /> 重新生成
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive"
                  onClick={removeWebhook}
                  disabled={saving}
                >
                  <Trash2 className="mr-1 size-3.5" /> 删除
                </Button>
              </div>
            </>
          )}
        </div>

        {cfg.hook_id && (
          <SheetFooter>
            <Button onClick={saveConfig} disabled={saving}>
              保存配置
            </Button>
          </SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  )
}
