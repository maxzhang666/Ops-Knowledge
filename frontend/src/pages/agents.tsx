import { EmptyState } from "@/components/shared/empty-state"
import { Bot } from "lucide-react"

export default function AgentsPage() {
  return (
    <EmptyState
      icon={<Bot className="h-12 w-12" />}
      title="智能体"
      description="智能体功能即将上线"
    />
  )
}
