import { api } from "./client"

// Plan 41 P19 — IngestionPlugin 元数据

export interface PluginCapabilities {
  supports_inline_edit: boolean
  supports_folder_tree: boolean
  supports_sync: boolean
  supports_batch_import: boolean
  ui_layout: "folder_tree" | "list_grid" | "table"
}

export interface SourceCapabilitiesEntry {
  source_type: string
  capabilities: PluginCapabilities
}

export const sourcesApi = {
  list: (): Promise<SourceCapabilitiesEntry[]> => api.get("/sources"),
}
