import { useEffect, useCallback } from "react"
import { useUiStore } from "@/stores/ui"

function applyTheme(theme: "light" | "dark" | "system") {
  const root = document.documentElement
  const isDark =
    theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)
  root.classList.toggle("dark", isDark)
}

export function useTheme() {
  const theme = useUiStore((s) => s.theme)
  const setTheme = useUiStore((s) => s.setTheme)

  useEffect(() => {
    applyTheme(theme)
    if (theme !== "system") return

    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const handler = () => applyTheme("system")
    mq.addEventListener("change", handler)
    return () => mq.removeEventListener("change", handler)
  }, [theme])

  const cycleTheme = useCallback(() => {
    const order: Array<"light" | "dark" | "system"> = ["light", "dark", "system"]
    const next = order[(order.indexOf(theme) + 1) % order.length]
    setTheme(next)
  }, [theme, setTheme])

  return { theme, setTheme, cycleTheme }
}
