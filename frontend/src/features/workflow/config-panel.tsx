import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { useEditorStore } from "./store"
import { VariableEditor } from "./variable-editor/editor"
import { ConditionsEditor } from "./editors/conditions"
import { CategoriesEditor } from "./editors/categories"
import { PromptTemplateEditor } from "./editors/prompt-template"
import { VariablesEditor } from "./editors/variables"
import { ParametersEditor } from "./editors/parameters"
import { KeyValueEditor } from "./editors/key-value"
import { JsonBodyEditor } from "./editors/json-body"
import {
  BuiltinToolsPicker,
  FolderPicker,
  KnowledgeBasePicker,
  LLMModelPicker,
  MCPServerPicker,
  ModelRegistryPicker,
} from "./editors/pickers"
import { InputBindingEditor } from "./editors/input-binding"

type SchemaValue = Record<string, unknown>

// Config-form fields that commonly embed `{{#node.field#}}` references.
// Note: Answer's answer / Template's template / HTTPRequest's url are
// INPUT bindings (handled by InputBindingEditor), not config fields —
// so this set is only for schema-declared strings that might reference
// variables (e.g. a node author later adds `x-variable-aware: true`).
const VARIABLE_AWARE_FIELDS = new Set<string>([])


export function ConfigPanel() {
  const selected = useEditorStore((s) => s.selected)
  const nodes = useEditorStore((s) => s.nodes)
  const catalog = useEditorStore((s) => s.catalog)
  const patchNodeData = useEditorStore((s) => s.patchNodeData)

  const node = nodes.find((n) => n.id === selected)
  if (!node) {
    return (
      <div className="p-4 text-sm text-muted-foreground">选中节点后编辑配置</div>
    )
  }

  const data = (node.data ?? {}) as Record<string, unknown>
  const entry = catalog.find((c) => c.manifest.type === data.nodeType)
  const schema = (entry?.config_form?.schema as SchemaValue | undefined) ?? {}
  const config = (data.config as Record<string, unknown>) ?? {}

  const properties =
    (schema.properties as Record<string, SchemaValue> | undefined) ?? {}

  // IO inputs — every entry declared in `io.inputs` needs a binding. These
  // land in DSL as `data.inputs[<name>]` rather than in the config schema,
  // so they need their own UI section.
  const ioInputs =
    (entry?.io?.inputs as Record<string, { type?: string }> | undefined) ?? {}
  const boundInputs =
    (config.inputs as Record<string, unknown> | undefined) ?? {}

  function setField(key: string, value: unknown) {
    patchNodeData(node!.id, { config: { ...config, [key]: value } })
  }

  function setFields(patch: Record<string, unknown>) {
    patchNodeData(node!.id, { config: { ...config, ...patch } })
  }

  function setInput(key: string, value: unknown) {
    const nextInputs = { ...boundInputs }
    if (value === undefined) {
      delete nextInputs[key]
    } else {
      nextInputs[key] = value
    }
    patchNodeData(node!.id, { config: { ...config, inputs: nextInputs } })
  }

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3 text-sm">
      <div>
        <div className="font-medium">
          {entry?.manifest.name ?? String(data.nodeType ?? "")}
        </div>
        <div className="text-xs text-muted-foreground">{node.id}</div>
      </div>

      {/* Input bindings — one per declared io.inputs key. Stored as
          data.inputs.<name> in DSL. Renders above config-form fields so
          authors bind data flow first, then tune parameters. */}
      {Object.keys(ioInputs).length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="text-xs font-medium text-muted-foreground">输入绑定</div>
          {Object.entries(ioInputs).map(([key, propSchema]) => (
            <InputBindingEditor
              key={key}
              name={key}
              schema={propSchema}
              value={boundInputs[key]}
              onChange={(v) => setInput(key, v)}
              currentNodeId={node.id}
            />
          ))}
        </div>
      )}

      {Object.keys(properties).length > 0 && (
        <div className="text-xs font-medium text-muted-foreground">配置</div>
      )}
      {Object.entries(properties).map(([key, propSchema]) => (
        <FieldRenderer
          key={key}
          name={key}
          schema={propSchema}
          value={config[key]}
          onChange={(v) => setField(key, v)}
          patchFields={setFields}
          currentNodeId={node.id}
          siblingConfig={config}
        />
      ))}
      {Object.keys(properties).length === 0 && Object.keys(ioInputs).length === 0 && (
        <p className="text-xs text-muted-foreground">此节点无可配置项</p>
      )}
    </div>
  )
}


function FieldRenderer({
  name,
  schema,
  value,
  onChange,
  patchFields,
  currentNodeId,
  siblingConfig,
}: {
  name: string
  schema: SchemaValue
  value: unknown
  onChange: (v: unknown) => void
  patchFields: (patch: Record<string, unknown>) => void
  currentNodeId: string
  siblingConfig: Record<string, unknown>
}) {
  const variableAware =
    VARIABLE_AWARE_FIELDS.has(name) || schema["x-variable-aware"] === true
  const type = schema.type as string | string[] | undefined
  const enumVals = schema.enum as unknown[] | undefined
  const label = (schema.title as string) ?? name

  // Specialty nested-array editors — take priority over the generic array
  // branch below. Matched by field name since the JSON Schema root object is
  // the same "type=object / items=object-with-fields" shape.
  if (name === "conditions") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <ConditionsEditor
          value={value as never}
          onChange={(v) => onChange(v)}
          currentNodeId={currentNodeId}
        />
      </div>
    )
  }
  if (name === "categories") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <CategoriesEditor
          value={value as never}
          onChange={(v) => onChange(v)}
        />
      </div>
    )
  }
  if (name === "prompt_template") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <PromptTemplateEditor
          value={value as never}
          onChange={(v) => onChange(v)}
          currentNodeId={currentNodeId}
        />
      </div>
    )
  }

  // Picker dispatches —— LLM 类节点统一用 LLMModelPicker 合并"供应商 + 模型"
  // 为一次选择；model_provider_id 字段本身不单独渲染，由 model_name 一并写入。
  if (name === "model_provider_id") {
    return null
  }
  if (name === "model_name") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">模型</Label>
        <LLMModelPicker
          providerId={siblingConfig.model_provider_id as string | undefined}
          modelName={value as string | undefined}
          kind="llm"
          onChange={(pid, mn) =>
            patchFields({ model_provider_id: pid, model_name: mn })
          }
        />
      </div>
    )
  }
  if (name === "model_registry_id") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <ModelRegistryPicker
          value={value as string | undefined}
          kind="llm"
          onChange={(v) => onChange(v)}
        />
      </div>
    )
  }
  if (name === "mcp_server_ids") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <MCPServerPicker
          value={(value as string[] | undefined) ?? []}
          onChange={(v) => onChange(v)}
        />
      </div>
    )
  }
  if (name === "builtin_tools") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <BuiltinToolsPicker
          value={(value as string[] | undefined) ?? []}
          onChange={(v) => onChange(v)}
        />
      </div>
    )
  }
  if (name === "knowledge_base_ids") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <KnowledgeBasePicker
          value={(value as string[] | undefined) ?? []}
          onChange={(v) => onChange(v)}
          multi
        />
      </div>
    )
  }
  if (name === "folder_ids") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <FolderPicker
          kbIds={(siblingConfig.knowledge_base_ids as string[] | undefined) ?? []}
          value={(value as string[] | undefined) ?? []}
          onChange={(v) => onChange(v)}
        />
      </div>
    )
  }
  if (name === "variables") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <VariablesEditor value={value as never} onChange={(v) => onChange(v)} />
      </div>
    )
  }
  if (name === "parameters") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <ParametersEditor value={value as never} onChange={(v) => onChange(v)} />
      </div>
    )
  }
  if (name === "headers" || name === "params" || name === "mapping") {
    const placeholders =
      name === "headers"
        ? { k: "Header", v: "Value" }
        : name === "params"
          ? { k: "参数名", v: "值（支持 {{#node.field#}}）" }
          : { k: "输出名", v: "路径，例如 chunks.0.content" }
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <KeyValueEditor
          value={value as Record<string, unknown> | undefined}
          onChange={(v) => onChange(v)}
          keyPlaceholder={placeholders.k}
          valuePlaceholder={placeholders.v}
        />
      </div>
    )
  }
  if (name === "body") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <JsonBodyEditor value={value} onChange={(v) => onChange(v)} />
      </div>
    )
  }

  if (enumVals) {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <select
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
        >
          <option value="">--</option>
          {enumVals.map((v) => (
            <option key={String(v)} value={String(v)}>
              {String(v)}
            </option>
          ))}
        </select>
      </div>
    )
  }

  if (type === "boolean") {
    return (
      <div className="flex items-center gap-2">
        <Switch checked={Boolean(value)} onCheckedChange={onChange} />
        <Label className="text-xs">{label}</Label>
      </div>
    )
  }

  if (type === "number" || type === "integer") {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <Input
          type="number"
          value={(value as number | undefined) ?? ""}
          onChange={(e) =>
            onChange(e.target.value === "" ? undefined : Number(e.target.value))
          }
        />
      </div>
    )
  }

  if (type === "array") {
    const arr = (value as unknown[] | undefined) ?? []
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <Textarea
          rows={3}
          placeholder="每行一项"
          value={arr.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join("\n")}
          onChange={(e) =>
            onChange(e.target.value.split("\n").filter(Boolean))
          }
        />
      </div>
    )
  }

  // Variable-aware text (e.g. Answer.answer, Template.template) → TipTap
  // editor with inline chips. Note: Code node uses Jinja (plain braces), not
  // our {{#node.field#}} syntax, so name==="code" stays with the raw Textarea.
  if (variableAware) {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <VariableEditor
          value={(value as string | undefined) ?? ""}
          onChange={(v) => onChange(v)}
          currentNodeId={currentNodeId}
          placeholder={`输入文本，{{ 或 / 插入变量`}
        />
      </div>
    )
  }

  // Multi-line defaults for code / template / JSON-looking strings.
  const isMultiline =
    name === "code" ||
    name === "template" ||
    (typeof value === "string" && value.includes("\n"))
  if (isMultiline) {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{label}</Label>
        <Textarea
          rows={6}
          value={(value as string | undefined) ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      <Label className="text-xs">{label}</Label>
      <Input
        value={(value as string | undefined) ?? ""}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}
