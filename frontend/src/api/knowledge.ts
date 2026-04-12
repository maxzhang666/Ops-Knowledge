import { api } from "./client"
import type { PaginatedResponse } from "./types"

// --- Interfaces ---

export type KBStatus = "active" | "indexing" | "error"
export type DocumentType = "pdf" | "docx" | "txt" | "md" | "html" | "csv" | "xlsx"
export type DocumentStatus = "pending" | "processing" | "completed" | "error"
export type ChunkLevel = "title" | "section" | "paragraph" | "sentence"
export type PresetType = "general" | "qa" | "book" | "tech" | "paper" | "custom"

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  status: KBStatus
  embedding_model: string
  doc_count: number
  chunk_count: number
  share_to_dept: boolean
  preset_type: PresetType
  created_at: string
  updated_at: string
}

export interface Folder {
  id: string
  kb_id: string
  name: string
  parent_id: string | null
  children?: Folder[]
  doc_count: number
  created_at: string
}

export interface Document {
  id: string
  kb_id: string
  folder_id: string | null
  name: string
  type: DocumentType
  status: DocumentStatus
  size: number
  chunk_count: number
  error_message?: string
  created_at: string
  updated_at: string
}

export interface Chunk {
  id: string
  document_id: string
  content: string
  level: ChunkLevel
  token_count: number
  quality_score: number
  is_edited: boolean
  order_index: number
  created_at: string
  updated_at: string
}

export interface RetrievalResult {
  chunk: Chunk
  score: number
  document_name: string
}

export interface RetrievalTestResponse {
  results: RetrievalResult[]
  elapsed_ms: number
}

// --- Request payloads ---

interface CreateKBPayload {
  name: string
  description?: string
  share_to_dept?: boolean
}

interface UpdateKBPayload {
  name?: string
  description?: string
  share_to_dept?: boolean
  preset_type?: PresetType
}

interface CreateFolderPayload {
  name: string
  parent_id?: string
}

interface EditChunkPayload {
  content: string
}

interface SplitChunkPayload {
  positions: number[]
}

interface MergeChunksPayload {
  chunk_ids: string[]
}

interface TestRetrievalPayload {
  query: string
  top_k?: number
}

// --- API ---

export const knowledgeApi = {
  // Knowledge Bases
  listKBs(params?: Record<string, string>) {
    return api.get<PaginatedResponse<KnowledgeBase>>("/knowledge-bases", params)
  },

  getKB(id: string) {
    return api.get<KnowledgeBase>(`/knowledge-bases/${id}`)
  },

  createKB(data: CreateKBPayload) {
    return api.post<KnowledgeBase>("/knowledge-bases", data)
  },

  updateKB(id: string, data: UpdateKBPayload) {
    return api.patch<KnowledgeBase>(`/knowledge-bases/${id}`, data)
  },

  deleteKB(id: string) {
    return api.delete<void>(`/knowledge-bases/${id}`)
  },

  // Folders
  listFolders(kbId: string) {
    return api.get<Folder[]>(`/knowledge-bases/${kbId}/folders`)
  },

  createFolder(kbId: string, data: CreateFolderPayload) {
    return api.post<Folder>(`/knowledge-bases/${kbId}/folders`, data)
  },

  // Documents
  listDocuments(kbId: string, params?: Record<string, string>) {
    return api.get<PaginatedResponse<Document>>(`/knowledge-bases/${kbId}/documents`, params)
  },

  getDocument(kbId: string, docId: string) {
    return api.get<Document>(`/knowledge-bases/${kbId}/documents/${docId}`)
  },

  uploadDocument(kbId: string, file: File, folderId?: string) {
    const formData = new FormData()
    formData.append("file", file)
    if (folderId) formData.append("folder_id", folderId)
    return api.upload<Document>(`/knowledge-bases/${kbId}/documents`, formData)
  },

  // Chunks
  listChunks(kbId: string, docId: string, params?: Record<string, string>) {
    return api.get<PaginatedResponse<Chunk>>(
      `/knowledge-bases/${kbId}/documents/${docId}/chunks`,
      params,
    )
  },

  editChunk(kbId: string, chunkId: string, data: EditChunkPayload) {
    return api.patch<Chunk>(`/knowledge-bases/${kbId}/chunks/${chunkId}`, data)
  },

  splitChunk(kbId: string, chunkId: string, data: SplitChunkPayload) {
    return api.post<Chunk[]>(`/knowledge-bases/${kbId}/chunks/${chunkId}/split`, data)
  },

  mergeChunks(kbId: string, data: MergeChunksPayload) {
    return api.post<Chunk>(`/knowledge-bases/${kbId}/chunks/merge`, data)
  },

  deleteChunk(kbId: string, chunkId: string) {
    return api.delete<void>(`/knowledge-bases/${kbId}/chunks/${chunkId}`)
  },

  // Retrieval Test
  testRetrieval(kbId: string, data: TestRetrievalPayload) {
    return api.post<RetrievalTestResponse>(`/knowledge-bases/${kbId}/retrieval-test`, data)
  },
}
