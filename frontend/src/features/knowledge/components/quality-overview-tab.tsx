import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { KnowledgeBase, KBStatus } from "@/api/knowledge"

const statusLabels: Record<KBStatus, { label: string; variant: "default" | "secondary" | "destructive" }> = {
  active: { label: "正常", variant: "default" },
  indexing: { label: "索引中", variant: "secondary" },
  error: { label: "异常", variant: "destructive" },
}

interface QualityOverviewTabProps {
  kb: KnowledgeBase
}

export function QualityOverviewTab({ kb }: QualityOverviewTabProps) {
  const status = statusLabels[kb.status]

  return (
    <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard title="文档总数" value={String(kb.doc_count)} />
      <StatCard title="分块总数" value={String(kb.chunk_count)} />
      <StatCard title="状态">
        <Badge variant={status.variant}>{status.label}</Badge>
      </StatCard>
      <StatCard title="嵌入模型">
        <Badge variant="secondary">{kb.embedding_model}</Badge>
      </StatCard>
    </div>
  )
}

function StatCard({ title, value, children }: { title: string; value?: string; children?: React.ReactNode }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-sm font-normal text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {value ? <p className="text-2xl font-semibold">{value}</p> : children}
      </CardContent>
    </Card>
  )
}
