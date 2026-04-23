import {
  Play,
  MessageSquare,
  Sparkles,
  GitBranch,
  Database,
  Repeat,
  KeySquare,
  Shuffle,
  Globe,
  Code2,
  FileText,
  Combine,
  Split,
  Megaphone,
  StickyNote,
  UserCheck,
  Box,
} from "lucide-react"

/**
 * 节点类型 → lucide 图标映射。初版凭语义各挑一个，后续可按 UI 调优替换。
 * 未命中时 fallback 为 Box（通用方盒）。
 */
const NODE_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  start: Play,
  answer: MessageSquare,
  llm: Sparkles,
  "if-else": GitBranch,
  "knowledge-retrieval": Database,
  iteration: Repeat,
  "parameter-extractor": KeySquare,
  "question-classifier": Shuffle,
  "http-request": Globe,
  code: Code2,
  template: FileText,
  "variable-aggregator": Combine,
  "variable-splitter": Split,
  "builtin.echo": Megaphone,
  note: StickyNote,
  human_approval: UserCheck,
}


export function NodeIcon({
  type,
  className = "size-3.5",
}: {
  type: string
  className?: string
}) {
  const Icon = NODE_ICON[type] ?? Box
  return <Icon className={className} />
}
