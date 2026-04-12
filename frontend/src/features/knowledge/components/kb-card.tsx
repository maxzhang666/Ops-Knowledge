import { useNavigate } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { TimeDisplay } from "@/components/shared/time-display"
import type { KnowledgeBase, KBStatus } from "@/api/knowledge"

const statusConfig: Record<KBStatus, { color: string; label: string }> = {
  active: { color: "bg-green-500", label: "正常" },
  indexing: { color: "bg-yellow-500", label: "索引中" },
  error: { color: "bg-red-500", label: "异常" },
}

interface KBCardProps {
  kb: KnowledgeBase
}

export function KBCard({ kb }: KBCardProps) {
  const navigate = useNavigate()
  const status = statusConfig[kb.status]

  return (
    <Card
      className="cursor-pointer transition-shadow hover:shadow-md"
      onClick={() => navigate(`/knowledge/${kb.id}`)}
    >
      <CardHeader>
        <div className="flex items-center gap-2">
          <span className={`inline-block h-2 w-2 rounded-full ${status.color}`} title={status.label} />
          <CardTitle className="truncate">{kb.name}</CardTitle>
        </div>
        {kb.description && (
          <CardDescription className="line-clamp-2">{kb.description}</CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary">{kb.embedding_model}</Badge>
          <span>{kb.doc_count} 文档</span>
          <span>{kb.chunk_count} 分块</span>
          <span className="ml-auto">
            <TimeDisplay value={kb.created_at} />
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
