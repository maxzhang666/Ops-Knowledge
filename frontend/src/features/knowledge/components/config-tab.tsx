import { useState } from "react"
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { knowledgeApi, type PresetType, type KnowledgeBase } from "@/api/knowledge"

interface PresetOption {
  type: PresetType
  name: string
  description: string
}

const presets: PresetOption[] = [
  { type: "general", name: "通用", description: "适合大部分场景的默认分块策略" },
  { type: "qa", name: "QA", description: "面向问答对格式，按问答对切分" },
  { type: "book", name: "书籍", description: "适合长篇书籍，按章节段落切分" },
  { type: "tech", name: "技术", description: "适合技术文档，保留代码块完整性" },
  { type: "paper", name: "论文", description: "适合学术论文，按摘要/章节切分" },
  { type: "custom", name: "自定义", description: "完全自定义分块规则" },
]

interface ConfigTabProps {
  kb: KnowledgeBase
  onUpdated: () => void
}

export function ConfigTab({ kb, onUpdated }: ConfigTabProps) {
  const [selected, setSelected] = useState<PresetType>(kb.preset_type)
  const [saving, setSaving] = useState(false)

  const changed = selected !== kb.preset_type

  async function handleSave() {
    setSaving(true)
    try {
      await knowledgeApi.updateKB(kb.id, { preset_type: selected })
      onUpdated()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-4 flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium">分块预设</h3>
        <p className="text-xs text-muted-foreground">选择适合文档类型的分块策略</p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {presets.map((preset) => (
          <Card
            key={preset.type}
            size="sm"
            className={cn(
              "cursor-pointer transition-all",
              selected === preset.type
                ? "ring-2 ring-primary"
                : "hover:ring-1 hover:ring-foreground/20",
            )}
            onClick={() => setSelected(preset.type)}
          >
            <CardHeader>
              <CardTitle>{preset.name}</CardTitle>
              <CardDescription>{preset.description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>

      {changed && (
        <div className="flex justify-end">
          <Button disabled={saving} onClick={handleSave}>
            {saving ? "保存中..." : "保存配置"}
          </Button>
        </div>
      )}
    </div>
  )
}
