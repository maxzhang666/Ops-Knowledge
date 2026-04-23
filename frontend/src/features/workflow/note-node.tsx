import { NodeResizer, type NodeProps, type Node } from "@xyflow/react"
import { useEditorStore } from "./store"

interface NoteData extends Record<string, unknown> {
  nodeType: "note"
  content: string
}

type NoteNodeType = Node<NoteData, "note">


/**
 * 便签节点 — 画布装饰，不参与工作流执行。
 *
 * 交互：
 *  - 顶部 2px 高的"标题条"作为拖动把手（textarea 加了 nodrag，
 *    所以节点本体只有这条可抓）。
 *  - 选中时显示 `NodeResizer` 四角/四边手柄，可拖拽调整大小。
 *  - 节点的 width/height 以 React Flow 的 `node.style` 保存，持久化走 DSL。
 */
export function NoteNode({ id, data, selected }: NodeProps<NoteNodeType>) {
  const patchNodeData = useEditorStore((s) => s.patchNodeData)

  return (
    <div
      className={`flex size-full flex-col rounded-md border bg-yellow-50 shadow-sm dark:bg-yellow-950/30 ${
        selected ? "border-yellow-500 ring-1 ring-yellow-500/30" : "border-yellow-300 dark:border-yellow-500/50"
      }`}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={100}
        minHeight={50}
        color="#eab308"
        lineStyle={{ borderWidth: 1 }}
        handleStyle={{ width: 6, height: 6, borderRadius: 2 }}
      />

      {/* 6px 标题条 — 纯拖动把手，无文字；顶部两角圆化以贴合外框 rounded-md
          的内侧（外框 6px - 1px border ≈ 5px），避免方块直角穿出圆角。 */}
      <div
        className="h-1.5 shrink-0 cursor-move rounded-t-[5px] bg-yellow-400 transition-colors hover:bg-yellow-500 dark:bg-yellow-600 dark:hover:bg-yellow-500"
        title="拖动移动便签"
      />

      <textarea
        value={data.content ?? ""}
        onChange={(e) => patchNodeData(id, { content: e.target.value })}
        // nodrag / nowheel 让 textarea 正常编辑而不触发画布平移/缩放。
        className="nodrag nowheel min-h-0 flex-1 resize-none bg-transparent p-1.5 text-[10px] leading-snug outline-none placeholder:text-yellow-700/50"
        placeholder="备注..."
      />
    </div>
  )
}
