import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  MiniMap,
  Panel as RFPanel,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { Input } from "@/components/ui/input"
import { OpskNode } from "./custom-node"
import { NoteNode } from "./note-node"
import { CanvasToolbar } from "./canvas-toolbar"
import { useEditorStore } from "./store"
import { categoryCn, nodeNameCn } from "./i18n"
import { autoLayout } from "./auto-layout"

const nodeTypes = { opsk: OpskNode, note: NoteNode }
const proOptions = { hideAttribution: true }
const fitViewOptions = { padding: 0.2, duration: 200 }

type CursorMode = "pan" | "select"


export function Canvas() {
  return (
    <ReactFlowProvider>
      <CanvasInner />
    </ReactFlowProvider>
  )
}


interface CtxMenu {
  x: number
  y: number
  // Where in the canvas the user right-clicked (pane coords), used as the
  // spawn position when creating a node from the menu.
  paneX: number
  paneY: number
  target: "pane" | "node" | "edge"
  targetId?: string
}


function CanvasInner() {
  const nodes = useEditorStore((s) => s.nodes)
  const edges = useEditorStore((s) => s.edges)
  const catalog = useEditorStore((s) => s.catalog)
  const setNodes = useEditorStore((s) => s.setNodes)
  const setEdges = useEditorStore((s) => s.setEdges)
  const select = useEditorStore((s) => s.select)
  const markDirty = useEditorStore((s) => s.markDirty)
  const draggingNodeType = useEditorStore((s) => s.draggingNodeType)
  const setDraggingNodeType = useEditorStore((s) => s.setDraggingNodeType)

  const { fitView, screenToFlowPosition } = useReactFlow()
  const didFit = useRef(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [ctx, setCtx] = useState<CtxMenu | null>(null)
  const [ctxFilter, setCtxFilter] = useState("")
  // 拖拽时画布内虚影的屏幕坐标（相对画布容器）。
  const [ghostPos, setGhostPos] = useState<{ x: number; y: number } | null>(null)
  // 光标模式：pan=手型（拖动画布），select=指针（拖动画框选择）。
  const [cursorMode, setCursorMode] = useState<CursorMode>("pan")

  // 画布挂载后首次拿到节点数据时才 fitView — 否则 embedded Panel 宽度未定，
  // 初始 fitView 会落在错误尺寸上，造成节点偏斜/过小。
  useEffect(() => {
    if (didFit.current || nodes.length === 0) return
    const t = window.setTimeout(() => {
      fitView({ padding: 0.2, duration: 0 })
      didFit.current = true
    }, 40)
    return () => window.clearTimeout(t)
  }, [nodes.length, fitView])

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      // 阻止删除 start（键盘 Delete / Backspace 或 React Flow 内部发起的 remove）。
      const filtered = changes.filter((c) => {
        if (c.type !== "remove") return true
        const n = nodes.find((x) => x.id === c.id)
        const nodeType = (n?.data as { nodeType?: string } | undefined)?.nodeType
        return nodeType !== "start"
      })
      setNodes(applyNodeChanges(filtered, nodes))
      if (filtered.some((c) => c.type !== "select")) markDirty()
    },
    [nodes, setNodes, markDirty],
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setEdges(applyEdgeChanges(changes, edges))
      if (changes.some((c) => c.type !== "select")) markDirty()
    },
    [edges, setEdges, markDirty],
  )

  const onConnect = useCallback(
    (conn: Connection) => {
      setEdges(addEdge(conn, edges))
      markDirty()
    },
    [edges, setEdges, markDirty],
  )

  const onDrop = useCallback(
    (ev: React.DragEvent) => {
      ev.preventDefault()
      const type = ev.dataTransfer.getData("application/node-type")
      setGhostPos(null)
      setDraggingNodeType(null)
      if (!type) return
      // 用 React Flow 的坐标换算，把屏幕坐标换成 flow 坐标（考虑 viewport 平移缩放）。
      const pos = screenToFlowPosition({ x: ev.clientX, y: ev.clientY })
      addNodeAt(type, pos)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [nodes, setNodes, markDirty, screenToFlowPosition, setDraggingNodeType],
  )

  const onDragOver = useCallback((ev: React.DragEvent) => {
    ev.preventDefault()
    ev.dataTransfer.dropEffect = "copy"
    const rect = (ev.currentTarget as HTMLElement).getBoundingClientRect()
    setGhostPos({ x: ev.clientX - rect.left, y: ev.clientY - rect.top })
  }, [])

  const onDragLeave = useCallback((ev: React.DragEvent) => {
    // 只在鼠标真正离开画布容器（而不是进入子元素）时清除。
    const related = ev.relatedTarget as HTMLElement | null
    const container = ev.currentTarget as HTMLElement
    if (related && container.contains(related)) return
    setGhostPos(null)
  }, [])

  function addNodeAt(type: string, pos: { x: number; y: number }) {
    const id = `${type}_${Date.now().toString(36)}`
    setNodes([
      ...nodes,
      {
        id,
        type: "opsk",
        position: pos,
        data: { nodeType: type, typeVersion: "1.0", config: {} },
      },
    ])
    markDirty()
  }

  /** 添加便签 — 放在当前视口中心位置，初始 140×70，用户可通过 NodeResizer 调整。 */
  function addNoteAtViewportCenter() {
    const el = containerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const pos = screenToFlowPosition({
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    })
    const id = `note_${Date.now().toString(36)}`
    setNodes([
      ...nodes,
      {
        id,
        type: "note",
        position: pos,
        data: { nodeType: "note", content: "" },
        style: { width: 140, height: 70 },
      },
    ])
    markDirty()
  }

  function handleAutoLayout() {
    if (nodes.length === 0) return
    setNodes(autoLayout(nodes, edges))
    markDirty()
    // 排列完成后自适应视图
    window.setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 50)
  }

  function removeNode(id: string) {
    // 开始节点（start）不允许删除。
    const n = nodes.find((x) => x.id === id)
    const nodeType = (n?.data as { nodeType?: string } | undefined)?.nodeType
    if (nodeType === "start") return
    setNodes(nodes.filter((n) => n.id !== id))
    setEdges(edges.filter((e) => e.source !== id && e.target !== id))
    markDirty()
  }

  function removeEdge(id: string) {
    setEdges(edges.filter((e) => e.id !== id))
    markDirty()
  }

  function closeCtx() {
    setCtx(null)
    setCtxFilter("")
  }

  // ---- Context menu — native DOM listener 避开 React 合成事件 -----------
  // 使用 React 的 onContextMenu 时，第一次右键经常不触发菜单（推测和
  // React Flow 在 pointer capture / d3-zoom 层的事件吞吐有关）。
  // 绑到 container 的 native listener，第一次就能 100% 命中。
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onCtx = (ev: MouseEvent) => {
      ev.preventDefault()
      const target = ev.target as HTMLElement
      const nodeEl = target.closest<HTMLElement>(".react-flow__node")
      const edgeEl = target.closest<HTMLElement>(".react-flow__edge")
      const rect = el.getBoundingClientRect()
      const paneX = ev.clientX - rect.left
      const paneY = ev.clientY - rect.top
      if (nodeEl) {
        const id = nodeEl.getAttribute("data-id") ?? ""
        if (id) setCtx({ x: ev.clientX, y: ev.clientY, paneX, paneY, target: "node", targetId: id })
        return
      }
      if (edgeEl) {
        const id = edgeEl.getAttribute("data-id") ?? ""
        if (id) setCtx({ x: ev.clientX, y: ev.clientY, paneX, paneY, target: "edge", targetId: id })
        return
      }
      setCtx({ x: ev.clientX, y: ev.clientY, paneX, paneY, target: "pane" })
      setCtxFilter("")
    }
    el.addEventListener("contextmenu", onCtx)
    return () => el.removeEventListener("contextmenu", onCtx)
  }, [])

  const filteredCatalog = useMemo(() => {
    const groups: Record<string, Array<{ type: string; name: string }>> = {}
    const kw = ctxFilter.toLowerCase()
    for (const e of catalog) {
      const m = e.manifest
      // 开始节点固定且唯一，不允许从右键菜单新增。
      if (m.type === "start") continue
      const display = nodeNameCn(m.type, m.name)
      if (
        kw &&
        !display.toLowerCase().includes(kw) &&
        !m.name.toLowerCase().includes(kw) &&
        !m.type.toLowerCase().includes(kw)
      ) {
        continue
      }
      (groups[m.category] ??= []).push({ type: m.type, name: display })
    }
    return groups
  }, [catalog, ctxFilter])

  const ghostLabel = draggingNodeType
    ? nodeNameCn(
        draggingNodeType,
        catalog.find((c) => c.manifest.type === draggingNodeType)?.manifest.name,
      )
    : null

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full"
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onClick={closeCtx}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, n) => select(n.id)}
        onPaneClick={() => { select(null); closeCtx() }}
        nodeTypes={nodeTypes}
        proOptions={proOptions}
        fitViewOptions={fitViewOptions}
        // 模式切换：pan=手型拖动画布；select=指针拖拽画框选择。
        panOnDrag={cursorMode === "pan"}
        selectionOnDrag={cursorMode === "select"}
      >
        <Background />
        <RFPanel position="bottom-left">
          <CanvasToolbar
            cursorMode={cursorMode}
            onCursorModeChange={setCursorMode}
            onAddNote={addNoteAtViewportCenter}
            onAutoLayout={handleAutoLayout}
          />
        </RFPanel>
        <MiniMap />
      </ReactFlow>

      {/* 拖拽虚影 — 从节点面板拖出时显示，跟随鼠标，drop 后消失。 */}
      {ghostPos && ghostLabel && (
        <div
          className="pointer-events-none absolute z-40 rounded-md border-2 border-dashed border-primary/70 bg-primary/5 px-3 py-2 text-xs font-medium text-primary shadow-sm"
          style={{
            left: ghostPos.x - 60,
            top: ghostPos.y - 16,
            minWidth: 120,
          }}
        >
          {ghostLabel}
        </div>
      )}

      {ctx && (
        <div
          // Fixed to viewport so the menu escapes canvas overflow clipping.
          style={{ position: "fixed", top: ctx.y, left: ctx.x, zIndex: 50 }}
          className="w-56 overflow-hidden rounded-md border bg-popover shadow-md"
          onClick={(e) => e.stopPropagation()}
          onContextMenu={(e) => e.preventDefault()}
        >
          {ctx.target === "node" && ctx.targetId && (() => {
            const targetNode = nodes.find((n) => n.id === ctx.targetId)
            const targetType = (targetNode?.data as { nodeType?: string } | undefined)?.nodeType
            if (targetType === "start") {
              return (
                <div className="px-3 py-2 text-xs text-muted-foreground">
                  开始节点不可删除
                </div>
              )
            }
            return (
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-xs text-destructive hover:bg-muted"
                onClick={() => { removeNode(ctx.targetId!); closeCtx() }}
              >
                删除节点
              </button>
            )
          })()}
          {ctx.target === "edge" && ctx.targetId && (
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-xs text-destructive hover:bg-muted"
              onClick={() => { removeEdge(ctx.targetId!); closeCtx() }}
            >
              删除连接
            </button>
          )}
          {ctx.target === "pane" && (
            <div className="flex flex-col">
              <div className="border-b p-2">
                <Input
                  autoFocus
                  value={ctxFilter}
                  onChange={(e) => setCtxFilter(e.target.value)}
                  placeholder="搜索节点..."
                  className="h-7 text-xs"
                />
              </div>
              <div className="max-h-64 overflow-y-auto p-1">
                {Object.entries(filteredCatalog).length === 0 ? (
                  <p className="px-2 py-1 text-[11px] text-muted-foreground">无匹配</p>
                ) : (
                  Object.entries(filteredCatalog).map(([cat, items]) => (
                    <div key={cat} className="mb-1">
                      <div className="px-2 py-1 text-[10px] text-muted-foreground">
                        {categoryCn(cat)}
                      </div>
                      {items.map((it) => (
                        <button
                          key={it.type}
                          type="button"
                          className="flex w-full items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted"
                          onClick={() => {
                            // 用 viewport 坐标换成 flow 坐标，节点才会落在右键位置。
                            const flowPos = screenToFlowPosition({ x: ctx.x, y: ctx.y })
                            addNodeAt(it.type, flowPos)
                            closeCtx()
                          }}
                        >
                          {it.name}
                        </button>
                      ))}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
