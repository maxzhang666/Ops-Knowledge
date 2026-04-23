import {
  Hand,
  LayoutGrid,
  Maximize2,
  MousePointer,
  StickyNote,
  ZoomIn,
  ZoomOut,
} from "lucide-react"
import { useReactFlow } from "@xyflow/react"
import { cn } from "@/lib/utils"


type CursorMode = "pan" | "select"

interface Props {
  cursorMode: CursorMode
  onCursorModeChange: (m: CursorMode) => void
  onAddNote: () => void
  onAutoLayout: () => void
}


/**
 * 画布左下角浮动工具栏 — 替代 ReactFlow 自带的暗色 `<Controls>`。
 *
 * 视觉：竖直卡片，尺寸 32×32 的按钮，lucide 图标 16px，tokens 跟项目主题；
 * 激活态高亮背景；悬停在按钮右侧弹出文字提示（纯 CSS，不依赖 tooltip 组件）。
 */
export function CanvasToolbar({
  cursorMode,
  onCursorModeChange,
  onAddNote,
  onAutoLayout,
}: Props) {
  const { zoomIn, zoomOut, fitView } = useReactFlow()

  return (
    <div className="flex flex-col overflow-hidden rounded-md border bg-card shadow-sm">
      <ToolButton label="放大" onClick={() => zoomIn({ duration: 200 })}>
        <ZoomIn className="size-4" />
      </ToolButton>
      <ToolButton label="缩小" onClick={() => zoomOut({ duration: 200 })}>
        <ZoomOut className="size-4" />
      </ToolButton>

      <Divider />

      <ToolButton
        label="手型（拖拽平移画布）"
        active={cursorMode === "pan"}
        onClick={() => onCursorModeChange("pan")}
      >
        <Hand className="size-4" />
      </ToolButton>
      <ToolButton
        label="指针（拖拽画框选择节点）"
        active={cursorMode === "select"}
        onClick={() => onCursorModeChange("select")}
      >
        <MousePointer className="size-4" />
      </ToolButton>

      <Divider />

      <ToolButton label="添加便签" onClick={onAddNote}>
        <StickyNote className="size-4" />
      </ToolButton>
      <ToolButton label="整理（自动排列节点）" onClick={onAutoLayout}>
        <LayoutGrid className="size-4" />
      </ToolButton>
      <ToolButton
        label="自适应（缩放查看全部节点）"
        onClick={() => fitView({ padding: 0.2, duration: 300 })}
      >
        <Maximize2 className="size-4" />
      </ToolButton>
    </div>
  )
}


function Divider() {
  return <div className="h-px bg-border" />
}


function ToolButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string
  active?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "flex size-9 items-center justify-center transition-colors",
          active
            ? "bg-primary text-primary-foreground"
            : "text-foreground/80 hover:bg-muted hover:text-foreground",
        )}
      >
        {children}
      </button>
      {/* 悬停文字提示 — 纯 CSS，位置在按钮右侧 */}
      <span
        className={cn(
          "pointer-events-none absolute left-full top-1/2 z-50 ml-2",
          "-translate-y-1/2 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-[11px] text-background shadow-md",
          "opacity-0 transition-opacity duration-150 group-hover:opacity-100",
        )}
      >
        {label}
      </span>
    </div>
  )
}
