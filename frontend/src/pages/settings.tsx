import { EmptyState } from "@/components/shared/empty-state"
import { Settings } from "lucide-react"

export default function SettingsPage() {
  return (
    <EmptyState
      icon={<Settings className="h-12 w-12" />}
      title="设置"
      description="系统设置功能即将上线"
    />
  )
}
