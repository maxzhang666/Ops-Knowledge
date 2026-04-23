import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

interface Props {
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
  categories: { name: string; description?: string }[]
}

/**
 * category 只能从 Agent classifier 已定义的类别里选——避免运营
 * 输入一个不存在的类别导致规则永不命中（spec 04 §LLM Classifier）。
 */
export function LLMIntentEditor({ value, onChange, categories }: Props) {
  const category = (value.category as string) ?? ""

  if (categories.length === 0) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-xs text-destructive">
        Agent 尚未配置 LLM 分类器或未定义任何类别。请先前往"意图分类器"菜单
        配置 ModelRegistry + 至少一个 category，然后回来创建此类规则。
      </div>
    )
  }

  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <Label className="text-[11px]">分类结果 = </Label>
      <Select value={category} onValueChange={(v) => v && onChange({ ...value, category: v })}>
        <SelectTrigger className="mt-1 h-8 text-xs">
          <SelectValue placeholder="选择类别" />
        </SelectTrigger>
        <SelectContent>
          {categories.map((c) => (
            <SelectItem key={c.name} value={c.name} className="text-xs">
              <span>{c.name}</span>
              {c.description && <span className="ml-2 text-muted-foreground">— {c.description}</span>}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="mt-2 text-[11px] text-muted-foreground">
        分类器会对用户消息做一次 LLM 调用（结果缓存）；置信度低于阈值时按
        fallback 策略处理。
      </p>
    </div>
  )
}
