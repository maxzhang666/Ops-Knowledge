import { useEffect, useState } from "react"
import { Input } from "@/components/ui/input"
import { workflowApi, type NodeCatalogEntry } from "@/api/workflow"
import { useEditorStore } from "./store"
import { categoryCn, nodeNameCn } from "./i18n"
import { NodeIcon } from "./node-icons"

// 1×1 透明图片 — 作为 HTML5 drag image 消除默认拖拽预览。
// 仅在浏览器环境下创建；SSR 安全（此组件只在客户端渲染）。
const EMPTY_DRAG_IMAGE =
  typeof window !== "undefined"
    ? (() => {
        const img = new Image()
        img.src =
          "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
        return img
      })()
    : (null as unknown as HTMLImageElement)

export function NodePalette() {
  const catalog = useEditorStore((s) => s.catalog)
  const setCatalog = useEditorStore((s) => s.setCatalog)
  const setDraggingNodeType = useEditorStore((s) => s.setDraggingNodeType)
  const [filter, setFilter] = useState("")

  useEffect(() => {
    if (catalog.length > 0) return
    workflowApi.nodeRegistry(false).then((res) => {
      if ("nodes" in res) setCatalog(res.nodes as NodeCatalogEntry[])
    })
  }, [catalog.length, setCatalog])

  const grouped: Record<string, NodeCatalogEntry[]> = {}
  const kw = filter.toLowerCase()
  for (const e of catalog) {
    // 开始节点（start）固定且唯一，由工作流自动创建，节点列表中不展示。
    if (e.manifest.type === "start") continue
    const display = nodeNameCn(e.manifest.type, e.manifest.name)
    if (
      kw &&
      !display.toLowerCase().includes(kw) &&
      !e.manifest.name.toLowerCase().includes(kw) &&
      !e.manifest.type.toLowerCase().includes(kw)
    ) {
      continue
    }
    grouped[e.manifest.category] ??= []
    grouped[e.manifest.category].push(e)
  }

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3 text-sm">
      <Input
        placeholder="搜索节点..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      {Object.entries(grouped).map(([cat, items]) => (
        <div key={cat}>
          <div className="mb-1 text-xs font-medium text-muted-foreground">
            {categoryCn(cat)}
          </div>
          <div className="space-y-1">
            {items.map((e) => (
              <div
                key={e.manifest.type}
                draggable
                onDragStart={(ev) => {
                  ev.dataTransfer.setData("application/node-type", e.manifest.type)
                  ev.dataTransfer.effectAllowed = "copy"
                  ev.dataTransfer.setDragImage(EMPTY_DRAG_IMAGE, 0, 0)
                  setDraggingNodeType(e.manifest.type)
                }}
                onDragEnd={() => setDraggingNodeType(null)}
                className="flex cursor-grab items-center gap-2 rounded-md border px-2 py-1 text-xs hover:bg-muted active:cursor-grabbing"
                title={e.manifest.description}
              >
                <NodeIcon type={e.manifest.type} className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 truncate">
                  {nodeNameCn(e.manifest.type, e.manifest.name)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
      {Object.keys(grouped).length === 0 && (
        <p className="text-xs text-muted-foreground">无匹配节点</p>
      )}
    </div>
  )
}
