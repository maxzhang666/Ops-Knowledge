import { api } from "./client"

// Milvus 治理面板（system 域）— 仅 system_admin 可访问

export interface MilvusKBHealth {
  kb_id: string
  kb_name: string
  source_type: string
  collection_exists: boolean
  milvus_count: number
  pg_count: number
  pg_unembedded: number
  /** milvus_count - pg_count，正数即可能存在孤儿（精确数走 scan_orphans 任务） */
  orphan_estimate: number
  kb_dim: number | null
  milvus_dim: number | null
  dim_matches: boolean
  embedding_model_id: string | null
  embedding_model_name: string | null
}

export type CeleryTaskState =
  | "PENDING" | "STARTED" | "SUCCESS" | "FAILURE" | "RETRY" | "REVOKED"

export interface MilvusTaskStatus {
  task_id: string
  state: CeleryTaskState
  /** SUCCESS 时 task 返回值（scan / clean 自定义结构） */
  result?: {
    status: string
    kb_id?: string
    milvus_count?: number
    pg_count?: number
    orphan_count?: number
    orphan_ids_preview?: string[]
    deleted?: number
    milvus_count_before?: number
    reason?: string
  }
  error?: string
}

export interface AsyncTaskAccept {
  task_id: string
  status: "accepted"
}

export const milvusGovApi = {
  overview: (): Promise<{ items: MilvusKBHealth[] }> =>
    api.get("/system/milvus/overview"),

  embeddingConsistency: (kb_id: string): Promise<MilvusKBHealth> =>
    api.get(`/system/milvus/${kb_id}/embedding_consistency`),

  scanOrphans: (kb_id: string): Promise<AsyncTaskAccept> =>
    api.post(`/system/milvus/${kb_id}/scan_orphans`),

  cleanOrphans: (kb_id: string): Promise<AsyncTaskAccept> =>
    api.post(`/system/milvus/${kb_id}/clean_orphans`),

  taskStatus: (task_id: string): Promise<MilvusTaskStatus> =>
    api.get(`/system/milvus/task/${task_id}/status`),
}
