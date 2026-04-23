import { create } from "zustand"
import type { Edge, Node } from "@xyflow/react"
import type { NodeCatalogEntry, WorkflowDetail } from "@/api/workflow"

export interface ExecutionSnapshot {
  id: string
  status: string
  nodes: Record<string, string>
  nodeErrors: Record<string, string>
  nodeOutputs: Record<string, unknown>
  // Per-node timing (ms epoch start, ms duration). Recorded from node_start
  // and node_end WS events so the UI can show "运行中 2.3s" / "完成 1.1s".
  nodeStartedAt: Record<string, number>
  nodeDurationMs: Record<string, number>
  stream: string[]
}

interface EditorState {
  workflow: WorkflowDetail | null
  nodes: Node[]
  edges: Edge[]
  selected: string | null
  dirty: boolean
  catalog: NodeCatalogEntry[]
  execution: ExecutionSnapshot | null
  // 节点面板拖拽中的节点类型（null 表示没在拖拽） — 供 Canvas 渲染虚影。
  draggingNodeType: string | null

  setWorkflow: (wf: WorkflowDetail) => void
  setCatalog: (cat: NodeCatalogEntry[]) => void
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  select: (id: string | null) => void
  patchNodeData: (id: string, patch: Record<string, unknown>) => void
  markDirty: () => void
  markClean: () => void
  setDraggingNodeType: (type: string | null) => void

  startExecution: (id: string) => void
  recordNodeStatus: (nodeId: string, status: string, error?: string) => void
  recordNodeOutput: (nodeId: string, output: unknown) => void
  recordNodeStart: (nodeId: string, ts: number) => void
  recordNodeEnd: (nodeId: string, ts: number) => void
  appendStreamChunk: (delta: string) => void
  finishExecution: (status: string) => void
  clearExecution: () => void
}

export const useEditorStore = create<EditorState>((set) => ({
  workflow: null,
  nodes: [],
  edges: [],
  selected: null,
  dirty: false,
  catalog: [],
  execution: null,
  draggingNodeType: null,

  setWorkflow: (wf) => set({ workflow: wf }),
  setCatalog: (catalog) => set({ catalog }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  select: (selected) => set({ selected }),
  patchNodeData: (id, patch) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...patch } } : n
      ),
      dirty: true,
    })),
  markDirty: () => set({ dirty: true }),
  markClean: () => set({ dirty: false }),
  setDraggingNodeType: (type) => set({ draggingNodeType: type }),

  startExecution: (id) =>
    set({
      execution: {
        id, status: "running", nodes: {}, nodeErrors: {},
        nodeOutputs: {}, nodeStartedAt: {}, nodeDurationMs: {}, stream: [],
      },
    }),
  recordNodeStatus: (nodeId, status, error) =>
    set((s) => {
      if (!s.execution) return {}
      const nextErrors = error
        ? { ...s.execution.nodeErrors, [nodeId]: error }
        : s.execution.nodeErrors
      return {
        execution: {
          ...s.execution,
          nodes: { ...s.execution.nodes, [nodeId]: status },
          nodeErrors: nextErrors,
        },
      }
    }),
  recordNodeOutput: (nodeId, output) =>
    set((s) => {
      if (!s.execution) return {}
      return {
        execution: {
          ...s.execution,
          nodeOutputs: { ...s.execution.nodeOutputs, [nodeId]: output },
        },
      }
    }),
  recordNodeStart: (nodeId, ts) =>
    set((s) => {
      if (!s.execution) return {}
      return {
        execution: {
          ...s.execution,
          nodeStartedAt: { ...s.execution.nodeStartedAt, [nodeId]: ts },
        },
      }
    }),
  recordNodeEnd: (nodeId, ts) =>
    set((s) => {
      if (!s.execution) return {}
      const started = s.execution.nodeStartedAt[nodeId]
      if (!started) return {}
      return {
        execution: {
          ...s.execution,
          nodeDurationMs: {
            ...s.execution.nodeDurationMs,
            [nodeId]: Math.max(0, ts - started),
          },
        },
      }
    }),
  appendStreamChunk: (delta) =>
    set((s) => {
      if (!s.execution) return {}
      return { execution: { ...s.execution, stream: [...s.execution.stream, delta] } }
    }),
  finishExecution: (status) =>
    set((s) => {
      if (!s.execution) return {}
      return { execution: { ...s.execution, status } }
    }),
  clearExecution: () => set({ execution: null }),
}))
