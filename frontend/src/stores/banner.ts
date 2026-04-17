import { create } from "zustand"

export type BannerKind = "quota" | "warning" | "info"

export interface BannerMessage {
  id: string
  kind: BannerKind
  title: string
  detail?: string
}

interface BannerState {
  banner: BannerMessage | null
  show: (msg: Omit<BannerMessage, "id">) => void
  dismiss: () => void
}

/**
 * Global banner slot — one at a time, sits above page content. Intended for
 * system-wide states the user must see (quota exhausted, degraded services).
 * Per-action feedback still goes through toast.
 */
export const useBannerStore = create<BannerState>((set) => ({
  banner: null,
  show(msg) {
    set({ banner: { ...msg, id: crypto.randomUUID() } })
  },
  dismiss() { set({ banner: null }) },
}))
