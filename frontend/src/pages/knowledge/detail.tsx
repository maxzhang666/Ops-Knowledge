import { useCallback, useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { BreadcrumbNav } from "@/components/layout/breadcrumb-nav"
import { FileTree } from "@/features/knowledge/components/file-tree"
import { DocumentList } from "@/features/knowledge/components/document-list"
import { ConfigTab } from "@/features/knowledge/components/config-tab"
import { RetrievalTestTab } from "@/features/knowledge/components/retrieval-test-tab"
import { QualityOverviewTab } from "@/features/knowledge/components/quality-overview-tab"
import { knowledgeApi, type KnowledgeBase, type Folder } from "@/api/knowledge"
import { useKnowledgeStore } from "@/stores/knowledge"

export default function KBDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { selectedFolderId, setCurrentKB, setSelectedFolder } = useKnowledgeStore()
  const [kb, setKb] = useState<KnowledgeBase | null>(null)
  const [folders, setFolders] = useState<Folder[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const [kbData, folderData] = await Promise.all([
        knowledgeApi.getKB(id),
        knowledgeApi.listFolders(id),
      ])
      setKb(kbData)
      setFolders(folderData)
      setCurrentKB(id)
    } finally {
      setLoading(false)
    }
  }, [id, setCurrentKB])

  useEffect(() => {
    load()
  }, [load])

  if (loading || !kb) {
    return <LoadingSpinner className="py-32" size="lg" />
  }

  return (
    <div>
      <BreadcrumbNav />
      <h1 className="mb-4 text-xl font-semibold">{kb.name}</h1>

      <Tabs defaultValue="documents">
        <TabsList>
          <TabsTrigger value="documents">文档</TabsTrigger>
          <TabsTrigger value="config">配置</TabsTrigger>
          <TabsTrigger value="retrieval">检索测试</TabsTrigger>
          <TabsTrigger value="quality">质量概览</TabsTrigger>
        </TabsList>

        <TabsContent value="documents">
          <div className="mt-4 flex gap-6">
            <aside className="w-56 shrink-0">
              <FileTree
                folders={folders}
                selectedFolderId={selectedFolderId}
                onSelectFolder={setSelectedFolder}
              />
            </aside>
            <div className="min-w-0 flex-1">
              <DocumentList kbId={kb.id} />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="config">
          <ConfigTab kb={kb} onUpdated={load} />
        </TabsContent>

        <TabsContent value="retrieval">
          <RetrievalTestTab kbId={kb.id} />
        </TabsContent>

        <TabsContent value="quality">
          <QualityOverviewTab kb={kb} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
