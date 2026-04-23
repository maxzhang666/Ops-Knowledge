import { useMemo, useState } from "react"
import { AlertCircle, CheckCircle2 } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface Props {
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
}

export function RegexEditor({ value, onChange }: Props) {
  const pattern = (value.pattern as string) ?? ""
  const flags = (value.flags as string) ?? ""
  const [probe, setProbe] = useState("")

  const compileError = useMemo(() => {
    if (!pattern) return null
    try {
      new RegExp(pattern, flags)
      return null
    } catch (e) {
      return e instanceof Error ? e.message : "invalid regex"
    }
  }, [pattern, flags])

  const probeResult = useMemo(() => {
    if (!pattern || !probe || compileError) return null
    try {
      return new RegExp(pattern, flags).test(probe)
    } catch {
      return null
    }
  }, [pattern, flags, probe, compileError])

  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <div className="grid grid-cols-[1fr_80px] gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-[11px]">正则</Label>
          <Input
            className="h-8 font-mono text-xs"
            value={pattern}
            onChange={(e) => onChange({ ...value, pattern: e.target.value })}
            placeholder="VPN|远程"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-[11px]">Flags</Label>
          <Input
            className="h-8 font-mono text-xs"
            value={flags}
            onChange={(e) => onChange({ ...value, flags: e.target.value.replace(/[^ims]/g, "") })}
            placeholder="i"
          />
        </div>
      </div>

      {compileError && (
        <div className="mt-2 flex items-center gap-1 text-[11px] text-destructive">
          <AlertCircle className="size-3" /> {compileError}
        </div>
      )}

      <div className="mt-3 flex items-center gap-2">
        <Input
          className="h-7 flex-1 text-xs"
          value={probe}
          onChange={(e) => setProbe(e.target.value)}
          placeholder="测试一段文本是否命中..."
        />
        {probeResult !== null && (
          <span className={`inline-flex items-center gap-1 text-xs ${probeResult ? "text-green-600" : "text-muted-foreground"}`}>
            {probeResult ? <><CheckCircle2 className="size-3" /> 命中</> : "未命中"}
          </span>
        )}
      </div>
    </div>
  )
}
