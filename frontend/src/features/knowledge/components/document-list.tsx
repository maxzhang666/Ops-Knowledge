import { useCallback, useEffect, useState } from "react"
import { FileText } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/shared/empty-state"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TimeDisplay } from "@/components/shared/time-display"
import { DocumentStatusBadge } from "./document-status-badge"
import { DocumentUpload } from "./document-upload"
import { knowledgeApi, type Document, type DocumentType } from "@/api/knowledge"
import { useKnowledgeStore } from "@/stores/knowledge"

const typeColors: Record<DocumentType, string> = {
  pdf: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  docx: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  txt: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  md: "bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300",
  html: "bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300",
  csv: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  xlsx: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
}

interface DocumentListProps {
  kbId: string
}

export function DocumentList({ kbId }: DocumentListProps) {
  const { selectedFolderId, setSelectedDoc } = useKnowledgeStore()
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)

  const loadDocs = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {}
      if (selectedFolderId) params.folder_id = selectedFolderId
      const res = await knowledgeApi.listDocuments(kbId, params)
      setDocs(res.items)
    } finally {
      setLoading(false)
    }
  }, [kbId, selectedFolderId])

  useEffect(() => {
    loadDocs()
  }, [loadDocs])

  if (loading) {
    return <LoadingSpinner className="py-16" />
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-muted-foreground">
          {docs.length} 个文档
        </h3>
        <DocumentUpload kbId={kbId} folderId={selectedFolderId} onUploaded={loadDocs} />
      </div>

      {docs.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-10 w-10" />}
          title="暂无文档"
          description="上传文档以开始构建知识库"
        />
      ) : (
        <div className="flex flex-col gap-1">
          {docs.map((doc) => (
            <button
              key={doc.id}
              type="button"
              className="flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors hover:bg-muted"
              onClick={() => setSelectedDoc(doc.id)}
            >
              <FileText className="size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{doc.name}</p>
                <p className="text-xs text-muted-foreground">
                  {doc.chunk_count} 分块
                  <span className="mx-1.5">-</span>
                  <TimeDisplay value={doc.created_at} />
                </p>
              </div>
              <Badge
                variant="outline"
                className={`shrink-0 border-transparent uppercase ${typeColors[doc.type]}`}
              >
                {doc.type}
              </Badge>
              <DocumentStatusBadge status={doc.status} />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
