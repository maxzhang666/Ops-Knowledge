import { api } from "./client"
import type { PaginatedResponse } from "./types"

// --- Interfaces ---

export type KBStatus = "active" | "indexing" | "error"
export type DocumentStatus = "pending" | "processing" | "completed" | "error"

export interface ChunkingConfig {
  [key: string]: unknown
}

export interface RetrievalConfig {
  [key: string]: unknown
}

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  embedding_model_id: string | null
  embedding_provider_id: string | null
  embedding_model_name: string | null
  chunking_config: ChunkingConfig | null
  retrieval_config: RetrievalConfig | null
  document_count: number
  chunk_count: number
  status: KBStatus
  created_by: string
  created_at: string
  updated_at: string
}

export interface Folder {
  id: string
  knowledge_base_id: string
  name: string
  parent_folder_id: string | null
  position: number
  children?: Folder[]
  created_at: string
}

export interface ProcessingProgress {
  stage: string
  completed: number
  total: number
}

export interface Document {
  id: string
  knowledge_base_id: string
  folder_id: string | null
  title: string
  source_type: string
  file_size: number
  file_hash: string | null
  status: DocumentStatus
  error_message: string | null
  processing_progress: ProcessingProgress | null
  chunk_count: number
  token_count: number
  position: number
  is_archived: boolean
  is_stale: boolean
  stale_since: string | null
  version: number
  processed_at: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface Chunk {
  id: string
  document_id: string
  knowledge_base_id: string
  folder_id: string | null
  content: string
  parent_chunk_id: string | null
  level: number
  position: number
  token_count: number
  quality_score: number | null
  vector_id: string | null
  is_manually_edited: boolean
  hit_count: number
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface ChunkSplitPreviewItem {
  content: string
  token_count: number
}

export interface RetrievalResult {
  chunk_id: string
  content: string
  score: number
  document_id: string
  folder_id: string | null
  level: number
  title: string
  metadata: Record<string, unknown> | null
  source_kb_id: string
}

export interface RetrievalTestResponse {
  query_used: string
  timing_ms: number
  total: number
  results: RetrievalResult[]
  indexed: boolean
}

// Governance (Plan 32 M2 + Plan 25 Layer 4)
export type GovernanceFacetKey =
  | "chunk_quality" | "coverage" | "freshness" | "availability" | "answer_quality"
export type GovernanceAlertSeverity = "info" | "warning" | "critical"
export type GovernanceAlertKind =
  | "stale_docs"
  | "low_quality_chunks"
  | "cold_chunks"
  | "knowledge_gap"
  | "redundancy"

export interface GovernanceFacet {
  score: number  // 0-100
  weight: number  // 0-1
  detail: Record<string, unknown>
}

export interface GovernanceAlert {
  severity: GovernanceAlertSeverity
  kind: GovernanceAlertKind
  title: string
  count: number
  preview: Array<Record<string, unknown>>
  action_href: string | null
}

export interface GovernanceTrendPoint { t: string; v: number }

export interface GovernanceHealth {
  kb_id: string
  health_score: number
  facets: Record<GovernanceFacetKey, GovernanceFacet>
  alerts: GovernanceAlert[]
  trend: { hits: GovernanceTrendPoint[]; adopted: GovernanceTrendPoint[] }
  generated_at: string
}

export interface GovernanceOverviewItem {
  kb_id: string
  kb_name: string
  health_score: number
  alerts_critical: number
  alerts_warning: number
}

export interface GovernanceOverview {
  kbs: GovernanceOverviewItem[]
  avg_health_score: number
  generated_at: string
}

export interface KBGovernanceConfig {
  expiration_threshold_days: number
  auto_archive_idle_days: number
}

// --- Request payloads ---

export interface CreateKBPayload {
  name: string
  description?: string
  embedding_model_id?: string
  embedding_provider_id?: string
  embedding_model_name?: string
  chunking_config?: ChunkingConfig
  retrieval_config?: RetrievalConfig
  share_to_dept?: boolean
}

interface UpdateKBPayload {
  name?: string
  description?: string
  embedding_model_id?: string
  embedding_provider_id?: string
  embedding_model_name?: string
  chunking_config?: ChunkingConfig
  retrieval_config?: RetrievalConfig
}

interface CreateFolderPayload {
  name: string
  parent_folder_id?: string
  position?: number
}

interface UpdateFolderPayload {
  name?: string
  parent_folder_id?: string | null
  position?: number
}

interface EditChunkPayload {
  content: string
}

interface SplitChunkPayload {
  split_positions: number[]
}

interface MergeChunksPayload {
  chunk_ids: string[]
}

interface AnnotateChunkPayload {
  tags?: string[] | null
  notes?: string | null
}

interface TestRetrievalPayload {
  query: string
  top_k?: number
  folder_ids?: string[]
}

interface BatchDeleteDocsPayload {
  ids: string[]
}

interface BatchMoveDocsPayload {
  ids: string[]
  target_folder_id: string | null
}

// --- API ---

export const knowledgeApi = {
  // Knowledge Bases
  listKBs(params?: Record<string, string>) {
    return api.get<PaginatedResponse<KnowledgeBase>>("/knowledge", params)
  },

  getKB(id: string) {
    return api.get<KnowledgeBase>(`/knowledge/${id}`)
  },

  createKB(data: CreateKBPayload) {
    return api.post<KnowledgeBase>("/knowledge", data)
  },

  updateKB(id: string, data: UpdateKBPayload, ifUnmodifiedSince?: string) {
    // Pass the KB's updated_at that the UI is based on; server rejects with
    // 409 if the KB was modified by someone else in between (optimistic lock).
    const headers = ifUnmodifiedSince ? { "If-Unmodified-Since": ifUnmodifiedSince } : undefined
    return api.post<KnowledgeBase>(`/knowledge/${id}/update`, data, headers)
  },

  deleteKB(id: string) {
    return api.post<void>(`/knowledge/${id}/delete`)
  },

  // Folders
  listFolders(kbId: string) {
    return api.get<Folder[]>(`/knowledge/${kbId}/folders`)
  },

  createFolder(kbId: string, data: CreateFolderPayload) {
    return api.post<Folder>(`/knowledge/${kbId}/folders`, data)
  },

  getFolder(kbId: string, folderId: string) {
    return api.get<Folder>(`/knowledge/${kbId}/folders/${folderId}`)
  },

  updateFolder(kbId: string, folderId: string, data: UpdateFolderPayload) {
    return api.post<Folder>(`/knowledge/${kbId}/folders/${folderId}/update`, data)
  },

  deleteFolder(kbId: string, folderId: string) {
    return api.post<void>(`/knowledge/${kbId}/folders/${folderId}/delete`)
  },

  // Documents
  listDocuments(kbId: string, params?: Record<string, string>) {
    return api.get<PaginatedResponse<Document>>(`/knowledge/${kbId}/documents`, params)
  },

  getDocument(kbId: string, docId: string) {
    return api.get<Document>(`/knowledge/${kbId}/documents/${docId}`)
  },

  uploadDocument(kbId: string, file: File, folderId?: string) {
    const formData = new FormData()
    formData.append("file", file)
    if (folderId) formData.append("folder_id", folderId)
    return api.upload<Document>(`/knowledge/${kbId}/documents`, formData)
  },

  batchDeleteDocuments(kbId: string, data: BatchDeleteDocsPayload) {
    return api.post<void>(`/knowledge/${kbId}/documents/batch/delete`, data)
  },

  batchMoveDocuments(kbId: string, data: BatchMoveDocsPayload) {
    return api.post<void>(`/knowledge/${kbId}/documents/batch/move`, data)
  },

  batchReprocessDocuments(kbId: string, data: { ids: string[] }) {
    return api.post<{ dispatched: number }>(`/knowledge/${kbId}/documents/batch/reprocess`, data)
  },

  previewDocument(kbId: string, docId: string) {
    return api.get<{ content: string }>(`/knowledge/${kbId}/documents/${docId}/preview`)
  },

  deleteDocument(kbId: string, docId: string) {
    return api.post<void>(`/knowledge/${kbId}/documents/${docId}/delete`)
  },

  reprocessDocument(kbId: string, docId: string) {
    return api.post<{ dispatched: number }>(`/knowledge/${kbId}/documents/${docId}/reprocess`)
  },

  // Plan 32 M3 生命周期
  documentImpact(kbId: string, docId: string) {
    return api.post<{
      n_chunks: number
      hits_7d: number
      top_frequency_chunks: Array<{ chunk_id: string; preview: string; hits_7d: number }>
      active_conversations_7d: number
    }>(`/knowledge/${kbId}/documents/${docId}/impact`)
  },

  archiveDocument(kbId: string, docId: string, archive: boolean) {
    return api.post<{ id: string; is_archived: boolean }>(
      `/knowledge/${kbId}/documents/${docId}/archive`,
      { archive },
    )
  },

  downloadDocument(kbId: string, docId: string) {
    return api.downloadBlob(`/knowledge/${kbId}/documents/${docId}/download`)
  },

  // Chunks
  listChunks(kbId: string, params?: Record<string, string>) {
    return api.get<PaginatedResponse<Chunk>>(`/knowledge/${kbId}/chunks`, params)
  },

  getChunk(kbId: string, chunkId: string) {
    return api.get<Chunk>(`/knowledge/${kbId}/chunks/${chunkId}`)
  },

  editChunk(kbId: string, chunkId: string, data: EditChunkPayload) {
    return api.post<Chunk>(`/knowledge/${kbId}/chunks/${chunkId}/update`, data)
  },

  deleteChunk(kbId: string, chunkId: string) {
    return api.post<void>(`/knowledge/${kbId}/chunks/${chunkId}/delete`)
  },

  splitChunk(kbId: string, chunkId: string, data: SplitChunkPayload) {
    return api.post<Chunk[]>(`/knowledge/${kbId}/chunks/${chunkId}/split`, data)
  },

  previewSplitChunk(kbId: string, chunkId: string, data: SplitChunkPayload) {
    return api.post<{ items: ChunkSplitPreviewItem[] }>(
      `/knowledge/${kbId}/chunks/${chunkId}/split/preview`, data,
    )
  },

  mergeChunks(kbId: string, data: MergeChunksPayload) {
    return api.post<Chunk>(`/knowledge/${kbId}/chunks/merge`, data)
  },

  annotateChunk(kbId: string, chunkId: string, data: AnnotateChunkPayload) {
    return api.post<Chunk>(`/knowledge/${kbId}/chunks/${chunkId}/annotate`, data)
  },

  // Retrieval Test
  testRetrieval(kbId: string, data: TestRetrievalPayload) {
    return api.post<RetrievalTestResponse>(`/knowledge/${kbId}/retrieval/test`, data)
  },

  // Coverage (Plan 26 Topic Distribution)
  listTopics(kbId: string) {
    return api.get<{
      kb_id: string
      topics: Array<{
        cluster_id: number
        label: string
        size: number
        keywords: string[]
        example_chunk_ids: string[]
        generated_at: string
      }>
    }>(`/knowledge/${kbId}/topics`)
  },

  // Governance (Plan 32 M2)
  governance(kbId: string) {
    return api.get<GovernanceHealth>(`/knowledge/${kbId}/governance`)
  },
  governanceOverview() {
    return api.get<GovernanceOverview>(`/knowledge/governance/overview`)
  },
  updateGovernanceConfig(kbId: string, cfg: KBGovernanceConfig) {
    return api.post<KBGovernanceConfig>(`/knowledge/${kbId}/governance/config`, cfg)
  },

  // Export / Import
  exportKB(kbId: string) {
    // Backend streams a ZIP — must read as Blob, not JSON.
    return api.postDownloadBlob(`/knowledge/${kbId}/export`)
  },

  importKB(data: FormData) {
    return api.upload<{ kb_id: string }>("/knowledge/import", data)
  },
}
