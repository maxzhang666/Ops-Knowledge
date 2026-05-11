import { useCallback, useEffect, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { BreadcrumbNav } from "@/components/layout/breadcrumb-nav"
import { FileTree } from "@/features/knowledge/components/file-tree"
import { DocumentList } from "@/features/knowledge/components/document-list"
import { DocumentDetailPanel } from "@/features/knowledge/components/document-detail-panel"
import { ConfigTab } from "@/features/knowledge/components/config-tab"
import { RetrievalTestTab } from "@/features/knowledge/components/retrieval-test-tab"
import { GovernanceTab } from "@/features/knowledge/components/governance-tab"
import { ReviewTab } from "@/features/knowledge/components/review-tab"
import { EntriesTab } from "@/features/knowledge/sources/entry/entries-tab"
import { knowledgeApi, type KnowledgeBase, type Folder } from "@/api/knowledge"
import { useKnowledgeStore } from "@/stores/knowledge"

const VALID_TABS = ["documents", "entries", "config", "retrieval", "governance", "review"] as const
type TabValue = typeof VALID_TABS[number]

export default function KBDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { selectedFolderId, selectedDocId, setCurrentKB, setSelectedFolder, setSelectedDoc } = useKnowledgeStore()
  const [kb, setKb] = useState<KnowledgeBase | null>(null)
  const [folders, setFolders] = useState<Folder[]>([])
  const [initLoading, setInitLoading] = useState(true)
  const [docsRefreshToken, setDocsRefreshToken] = useState(0)

  const handleDeleted = useCallback(() => {
    navigate("/knowledge", { replace: true })
  }, [navigate])

  // Tab state persisted in URL query so any accidental remount never falls back
  // to the default tab — and users can share deep links to a specific tab.
  // Default tab 按 KB.source_type 决定（条目型默认 entries，文件型默认 documents）
  const defaultTab: TabValue = kb?.source_type === "entry" ? "entries" : "documents"
  const activeTab: TabValue = (() => {
    const q = searchParams.get("tab")
    return VALID_TABS.includes(q as TabValue) ? (q as TabValue) : defaultTab
  })()

  function setActiveTab(v: string) {
    const next = new URLSearchParams(searchParams)
    next.set("tab", v)
    setSearchParams(next, { replace: true })
  }

  // Silent reload — used after save/update. Does NOT flip initLoading,
  // so the current view (including the active tab) stays put.
  const reload = useCallback(async () => {
    if (!id) return
    const [kbData, folderData] = await Promise.all([
      knowledgeApi.getKB(id),
      knowledgeApi.listFolders(id),
    ])
    setKb(kbData)
    setFolders(folderData)
  }, [id])

  const reloadFolders = useCallback(async () => {
    if (!id) return
    const folderData = await knowledgeApi.listFolders(id)
    setFolders(folderData)
  }, [id])

  // Initial fetch on id change — the only path that shows spinner.
  useEffect(() => {
    if (!id) return
    let cancelled = false
    setInitLoading(true)
    setCurrentKB(id)
    Promise.all([knowledgeApi.getKB(id), knowledgeApi.listFolders(id)])
      .then(([kbData, folderData]) => {
        if (cancelled) return
        setKb(kbData)
        setFolders(folderData)
      })
      .finally(() => { if (!cancelled) setInitLoading(false) })
    return () => { cancelled = true }
  }, [id, setCurrentKB])

  if (initLoading || !kb) {
    return <LoadingSpinner className="py-32" size="lg" />
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <BreadcrumbNav />
      <h1 className="mb-3 text-xl font-semibold">{kb.name}</h1>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex min-h-0 flex-1 flex-col">
        <TabsList>
          {/* Plan 41 — tabs 按 KB.source_type 动态渲染 */}
          {kb.source_type === "file" && (
            <TabsTrigger value="documents">文档</TabsTrigger>
          )}
          {kb.source_type === "entry" && (
            <TabsTrigger value="entries">条目</TabsTrigger>
          )}
          <TabsTrigger value="config">配置</TabsTrigger>
          <TabsTrigger value="retrieval">检索测试</TabsTrigger>
          <TabsTrigger value="governance">治理</TabsTrigger>
          {kb.review_required && (
            <TabsTrigger value="review">审批</TabsTrigger>
          )}
        </TabsList>

        {/* Documents tab — three-pane master-detail layout (file 型) */}
        {kb.source_type === "file" && <TabsContent value="documents" className="mt-4 flex min-h-0 flex-1 gap-3 overflow-hidden">
          {/* Col 1: file tree, 220px */}
          <aside className="h-full w-56 shrink-0 overflow-y-auto rounded-lg border bg-card p-2">
            <FileTree
              kbId={kb.id}
              folders={folders}
              selectedFolderId={selectedFolderId}
              onSelectFolder={(fid) => { setSelectedFolder(fid); setSelectedDoc(null) }}
              onFoldersChanged={reloadFolders}
            />
          </aside>

          {/* Col 2: document list, 320px */}
          <div className="h-full w-80 shrink-0 overflow-y-auto rounded-lg border bg-card p-3">
            <DocumentList
              kbId={kb.id}
              refreshToken={docsRefreshToken}
              onDocumentsChanged={() => setDocsRefreshToken((v) => v + 1)}
            />
          </div>

          {/* Col 3: document detail, flex-1 */}
          <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden rounded-lg border bg-card">
            {selectedDocId ? (
              <DocumentDetailPanel
                kbId={kb.id}
                docId={selectedDocId}
                onChanged={() => setDocsRefreshToken((v) => v + 1)}
                onClosed={() => setSelectedDoc(null)}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                选择文件查看详情与切片
              </div>
            )}
          </div>
        </TabsContent>}

        {kb.source_type === "entry" && <TabsContent value="entries" className="mt-4 min-h-0 flex-1 overflow-y-auto">
          <EntriesTab kb={kb} />
        </TabsContent>}

        <TabsContent value="config" className="mt-4 min-h-0 flex-1 overflow-y-auto">
          <ConfigTab kb={kb} onUpdated={reload} onDeleted={handleDeleted} />
        </TabsContent>

        <TabsContent value="retrieval" className="mt-4 min-h-0 flex-1 overflow-y-auto">
          <RetrievalTestTab kbId={kb.id} kbIndexed={(kb.chunk_count ?? 0) > 0} />
        </TabsContent>

        <TabsContent value="governance" className="mt-4 min-h-0 flex-1 overflow-y-auto">
          <GovernanceTab kb={kb} />
        </TabsContent>

        <TabsContent value="review" className="mt-4 min-h-0 flex-1 overflow-y-auto">
          <ReviewTab
            kb={kb}
            onPick={(docId) => { setSelectedDoc(docId); setActiveTab("documents") }}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
