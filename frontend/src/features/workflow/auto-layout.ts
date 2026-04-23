import type { Edge, Node } from "@xyflow/react"

/**
 * 简单 BFS 分层布局 — 从 trigger 节点出发，按拓扑层级从左到右排列；
 * 孤立节点（便签、未连接的草稿）追加到最后一层。
 *
 * 不引入 dagre/ELK 等外部依赖；对大多数 DAG 直觉上够用。
 */
const NODE_W = 200
const NODE_H = 120
const GAP_X = 80
const GAP_Y = 30


export function autoLayout(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes

  // 1. 从所有 start 节点 BFS 分层
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    if (!adj.has(e.source)) adj.set(e.source, [])
    adj.get(e.source)!.push(e.target)
  }

  const layer = new Map<string, number>()
  const starts = nodes.filter((n) => {
    const data = (n.data ?? {}) as { nodeType?: string }
    return data.nodeType === "start"
  })

  // 没有 start 时，以所有"无入边"节点为起点（保底）
  const incoming = new Set(edges.map((e) => e.target))
  const entryIds = starts.length
    ? starts.map((n) => n.id)
    : nodes.filter((n) => !incoming.has(n.id)).map((n) => n.id)

  const queue: Array<[string, number]> = entryIds.map((id) => [id, 0])
  while (queue.length) {
    const [id, d] = queue.shift()!
    const existing = layer.get(id)
    if (existing !== undefined && existing >= d) continue
    layer.set(id, d)
    for (const next of adj.get(id) ?? []) {
      queue.push([next, d + 1])
    }
  }

  // 2. 孤立 / 便签节点追加到最后一层
  const depths = Array.from(layer.values())
  const maxDepth = depths.length > 0 ? Math.max(...depths) : 0
  const orphanDepth = maxDepth + 1
  for (const n of nodes) {
    if (!layer.has(n.id)) layer.set(n.id, orphanDepth)
  }

  // 3. 按层分组，每层按原始 y 排序，稳定性更好
  const byLayer = new Map<number, string[]>()
  Array.from(layer.entries()).forEach(([id, d]) => {
    if (!byLayer.has(d)) byLayer.set(d, [])
    byLayer.get(d)!.push(id)
  })
  Array.from(byLayer.entries()).forEach(([, ids]) => {
    ids.sort((a: string, b: string) => {
      const na = nodes.find((x) => x.id === a)
      const nb = nodes.find((x) => x.id === b)
      return (na?.position.y ?? 0) - (nb?.position.y ?? 0)
    })
  })

  // 4. 分配坐标 — 每层纵向居中
  const pos = new Map<string, { x: number; y: number }>()
  Array.from(byLayer.entries()).forEach(([d, ids]) => {
    const totalH = ids.length * (NODE_H + GAP_Y) - GAP_Y
    ids.forEach((id: string, i: number) => {
      pos.set(id, {
        x: d * (NODE_W + GAP_X),
        y: i * (NODE_H + GAP_Y) - totalH / 2,
      })
    })
  })

  return nodes.map((n) => ({
    ...n,
    position: pos.get(n.id) ?? n.position,
  }))
}
