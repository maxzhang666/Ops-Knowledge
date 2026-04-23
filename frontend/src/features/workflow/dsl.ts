import type { Edge, Node } from "@xyflow/react"

export interface RawGraph {
  graph?: { nodes?: RawNode[]; edges?: RawEdge[] }
  workflow_variables?: Array<{ name: string; type: string; default?: unknown }>
  dsl_version?: string
}

interface RawNode {
  id: string
  type: string
  type_version?: string
  position?: { x: number; y: number }
  data?: Record<string, unknown>
  error_handling?: Record<string, unknown>
  blocks?: RawNode[]
  block_edges?: RawEdge[]
}

interface RawEdge {
  id?: string
  source: string
  target: string
  sourceHandle?: string | null
}

export function graphToFlow(graph: RawGraph | null | undefined): {
  nodes: Node[]
  edges: Edge[]
} {
  if (!graph?.graph) return { nodes: [], edges: [] }
  const nodes: Node[] = (graph.graph.nodes ?? []).map((n) => {
    // 便签节点 — 画布装饰，走独立的 NoteNode 渲染。
    if (n.type === "note") {
      const nd = (n.data as { content?: string; width?: number; height?: number } | undefined) ?? {}
      return {
        id: n.id,
        position: n.position ?? { x: 0, y: 0 },
        type: "note",
        data: {
          nodeType: "note",
          content: nd.content ?? "",
        },
        style: {
          width: typeof nd.width === "number" ? nd.width : 140,
          height: typeof nd.height === "number" ? nd.height : 70,
        },
      }
    }
    return {
      id: n.id,
      position: n.position ?? { x: 0, y: 0 },
      type: "opsk",
      // start 节点固定唯一，不可删除 — React Flow 原生尊重 `deletable: false`：
      // Delete/Backspace 键对它无效，也不会连带删除与它相连的 edge。
      deletable: n.type !== "start",
      data: {
        nodeType: n.type,
        typeVersion: n.type_version ?? "1.0",
        config: n.data ?? {},
        errorHandling: n.error_handling,
        blocks: n.blocks,
        blockEdges: n.block_edges,
      },
    }
  })
  const edges: Edge[] = (graph.graph.edges ?? []).map((e, i) => ({
    id: e.id ?? `e-${i}`,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle ?? undefined,
    type: "default",
    label: e.sourceHandle ?? undefined,
  }))
  return { nodes, edges }
}

/** Drop keys whose value is `undefined`. Pydantic `extra="forbid"` on the
 * backend will reject a payload where a declared-but-optional field is sent
 * as JSON `null` in some cases; and extra defensive cleanup against React
 * Flow leaking `measured` / `dragging` / `selected` metadata into our node
 * shape (they're only read from `n` directly, not `data`, but be paranoid). */
function compact<T extends Record<string, unknown>>(obj: T): T {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(obj)) {
    if (v !== undefined) out[k] = v
  }
  return out as T
}


export function flowToGraph(
  nodes: Node[],
  edges: Edge[],
  workflowVariables: RawGraph["workflow_variables"] = [],
): RawGraph {
  return {
    dsl_version: "1.0",
    graph: {
      nodes: nodes.map((n) => {
        const data = (n.data ?? {}) as Record<string, unknown>
        const nodeType = (data.nodeType as string) ?? "unknown"
        // 便签节点：保留 content + 尺寸（用户拖拽调整后的结果）；
        // 不含 config/errorHandling/blocks。
        if (nodeType === "note") {
          const style = (n as { style?: { width?: number; height?: number } }).style ?? {}
          return compact({
            id: n.id,
            type: "note",
            type_version: "1.0",
            position: n.position,
            data: {
              content: (data.content as string) ?? "",
              width: typeof style.width === "number" ? style.width : undefined,
              height: typeof style.height === "number" ? style.height : undefined,
            },
          }) as RawNode
        }
        return compact({
          id: n.id,
          type: nodeType,
          type_version: (data.typeVersion as string) ?? "1.0",
          position: n.position,
          data: (data.config as Record<string, unknown>) ?? {},
          error_handling: data.errorHandling as Record<string, unknown> | undefined,
          blocks: data.blocks as RawNode[] | undefined,
          block_edges: data.blockEdges as RawEdge[] | undefined,
        }) as RawNode
      }),
      edges: edges.map((e, i) =>
        compact({
          id: e.id ?? `e-${i}`,
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle ?? undefined,
        }) as RawEdge,
      ),
    },
    workflow_variables: workflowVariables ?? [],
  }
}
