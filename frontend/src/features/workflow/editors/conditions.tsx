import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { VariableSelector } from "../variable-editor/selector"

/**
 * Edits the If-Else node's `conditions: [{id, logic, rules: [{variable, operator, value}]}]`.
 * `variable` 是 DSL selector 数组 `["node_id", "field"]`；后端 _if_else._eval_rule
 * 已支持 list 形式（走 resolve_selector），不再使用裸字符串。
 */

const OPERATORS: Array<{ value: string; label: string }> = [
  { value: "eq", label: "= 等于" },
  { value: "neq", label: "≠ 不等于" },
  { value: "gt", label: "> 大于" },
  { value: "gte", label: "≥ 大于等于" },
  { value: "lt", label: "< 小于" },
  { value: "lte", label: "≤ 小于等于" },
  { value: "contains", label: "包含" },
  { value: "not_contains", label: "不包含" },
  { value: "is_empty", label: "为空" },
  { value: "not_empty", label: "非空" },
  { value: "starts_with", label: "以…开头" },
  { value: "ends_with", label: "以…结尾" },
]

// 这些 operator 不需要"比较值"输入框。
const UNARY_OPS = new Set(["is_empty", "not_empty"])

interface Rule {
  variable: string[] | undefined  // DSL selector ["node_id", "field"]
  operator: string
  value?: unknown
}

interface Condition {
  id: string
  logic: "and" | "or"
  rules: Rule[]
}


export function ConditionsEditor({
  value,
  onChange,
  currentNodeId,
}: {
  value: Condition[] | undefined
  onChange: (next: Condition[]) => void
  currentNodeId: string
}) {
  const conditions = value ?? []

  function update(idx: number, patch: Partial<Condition>) {
    onChange(conditions.map((c, i) => (i === idx ? { ...c, ...patch } : c)))
  }

  function removeCondition(idx: number) {
    onChange(conditions.filter((_, i) => i !== idx))
  }

  function addCondition() {
    onChange([
      ...conditions,
      { id: `cond_${conditions.length + 1}`, logic: "and", rules: [] },
    ])
  }

  function updateRule(cidx: number, ridx: number, patch: Partial<Rule>) {
    update(cidx, {
      rules: conditions[cidx].rules.map((r, i) =>
        i === ridx ? { ...r, ...patch } : r,
      ),
    })
  }

  function addRule(cidx: number) {
    update(cidx, {
      rules: [
        ...conditions[cidx].rules,
        { variable: undefined, operator: "eq", value: "" },
      ],
    })
  }

  function removeRule(cidx: number, ridx: number) {
    update(cidx, { rules: conditions[cidx].rules.filter((_, i) => i !== ridx) })
  }

  return (
    <div className="space-y-3">
      {conditions.map((c, cidx) => (
        <div key={cidx} className="space-y-2 rounded-md border p-2">
          {/* 标题行：只有分支 ID + 删除 — AND/OR 逻辑移到规则之间。 */}
          <div className="flex items-center gap-2">
            <Input
              value={c.id}
              onChange={(e) => update(cidx, { id: e.target.value })}
              placeholder="分支 ID"
              className="h-7 flex-1 text-xs"
            />
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => removeCondition(cidx)}
            >
              <Trash2 className="size-3.5 text-destructive" />
            </Button>
          </div>
          <div className="space-y-2">
            {/* 规则列表 — 多条规则时左侧花括号把它们整体括起来，中点贴「且/或」胶囊。 */}
            <div className={c.rules.length >= 2 ? "relative pl-12" : ""}>
              {c.rules.length >= 2 && (
                <>
                  {/* 花括号 `[`：顶横 + 竖线 + 底横，都以 left:14px 为轴；
                      横线从竖线顶/底端向右延伸，指向右侧的规则内容。 */}
                  <div
                    aria-hidden
                    className="absolute left-[14px] top-2 h-[2px] w-3 rounded-full bg-border"
                  />
                  <div
                    aria-hidden
                    className="absolute bottom-2 left-[14px] top-2 w-[2px] -translate-x-1/2 rounded-full bg-border"
                  />
                  <div
                    aria-hidden
                    className="absolute bottom-2 left-[14px] h-[2px] w-3 rounded-full bg-border"
                  />
                  {/* Switch 中心对齐到竖线中心（left:14px）。 */}
                  <div className="absolute left-[14px] top-1/2 -translate-x-1/2 -translate-y-1/2">
                    <LogicSwitch
                      value={c.logic}
                      onChange={(v) => update(cidx, { logic: v })}
                    />
                  </div>
                </>
              )}
              <div className="space-y-2">
                {c.rules.map((r, ridx) => {
                  const unary = UNARY_OPS.has(r.operator)
                  return (
                    <div key={ridx} className="space-y-1 rounded-md bg-muted/20 p-1.5">
                      {/* 第一行：变量 + 操作符 + 删除 */}
                      <div className="flex flex-wrap items-center gap-1">
                        <VariableSelector
                          currentNodeId={currentNodeId}
                          value={r.variable}
                          onChange={(v) => updateRule(cidx, ridx, { variable: v })}
                          placeholder="选择变量"
                        />
                        <select
                          value={r.operator}
                          onChange={(e) =>
                            updateRule(cidx, ridx, { operator: e.target.value })
                          }
                          className="h-7 rounded-md border border-input bg-background px-2 text-xs"
                        >
                          {OPERATORS.map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="ml-auto h-7 w-7"
                          onClick={() => removeRule(cidx, ridx)}
                        >
                          <Trash2 className="size-3.5 text-destructive" />
                        </Button>
                      </div>
                      {/* 第二行：比较值 —— 单元操作符（为空/非空）不需要值 */}
                      {!unary && (
                        <Input
                          value={(r.value as string | undefined) ?? ""}
                          onChange={(e) => updateRule(cidx, ridx, { value: e.target.value })}
                          placeholder="比较值"
                          className="h-7 w-full text-xs"
                        />
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
            {/* + 规则 按钮放在花括号外部 —— 它不属于规则集合本身。 */}
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => addRule(cidx)}
            >
              <Plus className="mr-1 size-3" /> 规则
            </Button>
          </div>
        </div>
      ))}
      <div>
        <Button variant="outline" size="sm" onClick={addCondition}>
          <Plus className="mr-1 size-3.5" /> 添加条件
        </Button>
        <p className="mt-1 text-xs text-muted-foreground">
          不匹配任何条件时走 <code>else</code> 分支
        </p>
      </div>
    </div>
  )
}


/**
 * 竖向"且 / 或"开关 —— 两个标签上下排列，当前选中项高亮背景；点击切换到另一个。
 * 相比下拉只占 ~16px 宽度，节省花括号旁的横向空间。
 */
function LogicSwitch({
  value,
  onChange,
}: {
  value: "and" | "or"
  onChange: (v: "and" | "or") => void
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(value === "and" ? "or" : "and")}
      className="flex flex-col overflow-hidden rounded-full border border-input bg-background shadow-sm"
      title="多条规则之间的逻辑关系（点击切换）"
    >
      <span
        className={`flex h-6 w-6 items-center justify-center text-[11px] font-bold transition-colors ${
          value === "and"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground"
        }`}
      >
        且
      </span>
      <span
        className={`flex h-6 w-6 items-center justify-center text-[11px] font-bold transition-colors ${
          value === "or"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground"
        }`}
      >
        或
      </span>
    </button>
  )
}
