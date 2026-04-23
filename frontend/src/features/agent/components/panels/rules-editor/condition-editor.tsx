/**
 * form-based 条件编辑器：path 下拉（仅 trusted 白名单）+ op 下拉 + value。
 *
 * **产品约束**：绝不让运营手写 JSONLogic / 自由表达式。非白名单 path
 * 禁止使用（spec 04 §Metadata trust）。
 */
import { useEffect, useMemo } from "react"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import type { ConditionOp } from "@/api/orchestrator"

interface Props {
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
  trustedPaths: string[]
}

const OPS: { value: ConditionOp; label: string; listValue: boolean }[] = [
  { value: "==", label: "等于", listValue: false },
  { value: "!=", label: "不等于", listValue: false },
  { value: "in", label: "包含于", listValue: true },
  { value: "not_in", label: "不包含于", listValue: true },
  { value: ">", label: ">", listValue: false },
  { value: "<", label: "<", listValue: false },
  { value: ">=", label: ">=", listValue: false },
  { value: "<=", label: "<=", listValue: false },
]

export function ConditionEditor({ value, onChange, trustedPaths }: Props) {
  const path = (value.path as string) || trustedPaths[0] || ""
  const op = (value.op as ConditionOp) || "=="
  const rawValue = value.value

  const opInfo = useMemo(() => OPS.find((o) => o.value === op) ?? OPS[0], [op])

  // Seed path if current path is no longer in trusted list (e.g. admin shrank whitelist)
  useEffect(() => {
    if (!trustedPaths.includes(path) && trustedPaths.length > 0) {
      onChange({ ...value, path: trustedPaths[0] })
    }
  }, [path, trustedPaths])  // eslint-disable-line react-hooks/exhaustive-deps

  function setPath(p: string) {
    onChange({ ...value, path: p })
  }
  function setOp(newOp: ConditionOp) {
    // List-op ↔ scalar-op: coerce value accordingly
    const info = OPS.find((o) => o.value === newOp)!
    let next = rawValue
    if (info.listValue && !Array.isArray(next)) next = next != null && next !== "" ? [String(next)] : []
    if (!info.listValue && Array.isArray(next)) next = next[0] ?? ""
    onChange({ ...value, op: newOp, value: next })
  }
  function setValueScalar(v: string) {
    // Parse as number if looks numeric; else string
    const num = Number(v)
    onChange({ ...value, value: v !== "" && !Number.isNaN(num) ? num : v })
  }
  function setValueList(csv: string) {
    const list = csv.split(",").map((s) => s.trim()).filter(Boolean)
    onChange({ ...value, value: list })
  }

  if (trustedPaths.length === 0) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-xs text-destructive">
        未配置可信 metadata 路径。请先前往"意图分类器"菜单配置，或由管理员在
        Agent orchestrator_config.trusted_metadata_paths 添加路径。
      </div>
    )
  }

  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <div className="grid grid-cols-3 gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-[11px]">路径（仅受信字段）</Label>
          <Select value={path} onValueChange={(v) => v && setPath(v)}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {trustedPaths.map((p) => (
                <SelectItem key={p} value={p} className="text-xs">
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-[11px]">操作符</Label>
          <Select value={op} onValueChange={(v) => v && setOp(v as ConditionOp)}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {OPS.map((o) => (
                <SelectItem key={o.value} value={o.value} className="text-xs">
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-[11px]">{opInfo.listValue ? "值列表（逗号分隔）" : "值"}</Label>
          {opInfo.listValue ? (
            <Input
              className="h-8 text-xs"
              value={Array.isArray(rawValue) ? rawValue.join(", ") : ""}
              onChange={(e) => setValueList(e.target.value)}
              placeholder="admin, ops"
            />
          ) : (
            <Input
              className="h-8 text-xs"
              value={rawValue != null ? String(rawValue) : ""}
              onChange={(e) => setValueScalar(e.target.value)}
              placeholder="admin"
            />
          )}
        </div>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        只能匹配受信字段（系统注入，调用方无法伪造）。其他字段见"Agent 配置 → 意图分类器"页扩展白名单。
      </p>
    </div>
  )
}
