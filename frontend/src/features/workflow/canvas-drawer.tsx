import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"

/**
 * Canvas 级浮层抽屉容器 — 外观圆角卡片，非模态，不挤压画布。
 *
 * 用法：父层容器用 `absolute inset-y-0 right-0 flex gap-2 py-2 pr-2 pointer-events-none`
 * 把一组抽屉悬浮到画布右侧；本组件内部自管 `pointer-events-auto`，
 * 未展开时 `width=0` 不吃事件、不占可见宽度。
 *
 * 动画：默认 width transition 250ms；传 `animated={false}` 可切换为直接渲染，
 * 适合节点配置面板这类不需要滑入感的场景。
 */
interface Props {
  open: boolean
  width?: number
  animated?: boolean
  keepMounted?: boolean
  children: React.ReactNode
}


export function CanvasDrawer({
  open,
  width = 360,
  animated = true,
  keepMounted = false,
  children,
}: Props) {
  // open=true 立刻挂载；open=false 等动画结束再卸载（无动画时立即卸载）。
  const [mounted, setMounted] = useState(open)
  useEffect(() => {
    if (open) {
      setMounted(true)
      return
    }
    if (!animated) {
      setMounted(false)
      return
    }
    const t = window.setTimeout(() => setMounted(false), 260)
    return () => window.clearTimeout(t)
  }, [open, animated])

  const shouldRender = open || mounted || keepMounted

  return (
    <div
      aria-hidden={!open}
      className={cn(
        "h-full shrink-0 overflow-hidden rounded-lg border bg-card shadow-sm",
        open ? "pointer-events-auto" : "pointer-events-none border-transparent shadow-none",
        animated ? "transition-[width] ease-out" : "",
      )}
      style={{
        width: open ? width : 0,
        transitionDuration: animated ? "250ms" : undefined,
      }}
    >
      <div style={{ width }} className="h-full">
        {shouldRender ? children : null}
      </div>
    </div>
  )
}
