import { EmptyState } from "@/components/shared/empty-state"
import { BookOpen } from "lucide-react"

export default function KnowledgePage() {
  return (
    <EmptyState
      icon={<BookOpen className="h-12 w-12" />}
      title="知识库"
      description="知识库功能即将上线"
    />
  )
}
