import { useNavigate } from "react-router-dom"
import { MoreHorizontal, Trash2, Settings2, Download } from "lucide-react"
import { toast } from "sonner"

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { TimeDisplay } from "@/components/shared/time-display"
import { knowledgeApi, type KnowledgeBase, type KBStatus } from "@/api/knowledge"

const statusConfig: Record<KBStatus, { color: string; label: string }> = {
  active: { color: "bg-success", label: "正常" },
  indexing: { color: "bg-warning", label: "索引中" },
  error: { color: "bg-destructive", label: "异常" },
}

interface KBCardProps {
  kb: KnowledgeBase
  onDelete: (kb: KnowledgeBase) => void
}

async function handleExport(kb: KnowledgeBase) {
  try {
    const blob = await knowledgeApi.exportKB(kb.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${kb.name}.oka`
    a.click()
    URL.revokeObjectURL(url)
    toast.success(`已导出 ${kb.name}.oka`)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "导出失败")
  }
}

export function KBCard({ kb, onDelete }: KBCardProps) {
  const navigate = useNavigate()
  const status = statusConfig[kb.status]

  return (
    <Card
      className="group cursor-pointer transition-shadow hover:shadow-elevation-2"
      onClick={() => navigate(`/knowledge/${kb.id}`)}
    >
      <CardHeader>
        <div className="flex items-start gap-2">
          <span
            className={`mt-2 inline-block h-2 w-2 shrink-0 rounded-full ${status.color}`}
            title={status.label}
          />
          <CardTitle className="min-w-0 flex-1 truncate">{kb.name}</CardTitle>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  className="inline-flex size-7 shrink-0 items-center justify-center rounded opacity-0 transition-opacity hover:bg-accent group-hover:opacity-100 data-[state=open]:opacity-100"
                  title="操作"
                  onClick={(e) => e.stopPropagation()}
                />
              }
            >
              <MoreHorizontal className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="text-sm" onClick={(e) => e.stopPropagation()}>
              <DropdownMenuItem
                onClick={(e) => { e.stopPropagation(); navigate(`/knowledge/${kb.id}?tab=config`) }}
              >
                <Settings2 className="mr-2 size-3.5" /> 配置
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={(e) => { e.stopPropagation(); handleExport(kb) }}
              >
                <Download className="mr-2 size-3.5" /> 导出 .oka
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={(e) => { e.stopPropagation(); onDelete(kb) }}
                className="text-destructive"
              >
                <Trash2 className="mr-2 size-3.5" /> 删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        {kb.description && (
          <CardDescription className="line-clamp-2">{kb.description}</CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary">{kb.embedding_model_name ?? "未配置"}</Badge>
          <span>{kb.document_count} 文档</span>
          <span>{kb.chunk_count} 分块</span>
          <span className="ml-auto">
            <TimeDisplay value={kb.created_at} />
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
