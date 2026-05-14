import { api } from "./client"

// Spec 25 §2.6 — KB 级标签配置 + 3 档 preset

export type TagPreset = "low_cost" | "balanced" | "high_quality" | "custom"

export interface KBTagSettings {
  kb_id: string
  preset: TagPreset
  auto_tag_enabled: boolean
  auto_tag_provider: "keybert" | "llm" | "hybrid"
  auto_tag_llm_model_id: string | null
  auto_tag_max_per_unit: number
  auto_tag_confidence_threshold: number
  tag_filter_enabled: boolean
  tag_boost_weight: number
  tag_routing_enabled: boolean
}

export interface UpdateKBTagSettings {
  preset?: Exclude<TagPreset, "custom">
  auto_tag_enabled?: boolean
  auto_tag_provider?: KBTagSettings["auto_tag_provider"]
  auto_tag_llm_model_id?: string | null
  auto_tag_max_per_unit?: number
  auto_tag_confidence_threshold?: number
  tag_filter_enabled?: boolean
  tag_boost_weight?: number
  tag_routing_enabled?: boolean
}

export const kbTagSettingsApi = {
  get: (kbId: string): Promise<KBTagSettings> =>
    api.get(`/knowledge/${kbId}/tag-settings`),

  update: (kbId: string, body: UpdateKBTagSettings): Promise<KBTagSettings> =>
    api.post(`/knowledge/${kbId}/tag-settings/update`, body),
}
