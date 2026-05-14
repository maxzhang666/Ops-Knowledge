import { api } from "./client"

// Spec 25 Plan E — KB 标签治理总览

export interface TagCloudItem {
  canonical: string
  usage_count: number
}

export interface TagGovernanceOverview {
  dictionary_size: number
  deprecated_size: number
  tag_cloud: TagCloudItem[]

  total_chunks: number
  orphan_chunks: number
  orphan_ratio: number

  total_entries: number
  entries_with_auto_tags: number

  accept_count_30d: number
  reject_count_30d: number
  accept_ratio_30d: number | null

  retrieval_total_30d: number
  routing_used_30d: number
  boost_used_30d: number
  tag_filter_used_30d: number
}

export const tagGovernanceApi = {
  overview: (kbId: string): Promise<TagGovernanceOverview> =>
    api.get(`/knowledge/${kbId}/tag-governance/overview`),
}
