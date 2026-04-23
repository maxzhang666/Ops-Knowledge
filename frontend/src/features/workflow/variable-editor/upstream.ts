import type { Edge, Node } from "@xyflow/react"
import type { NodeCatalogEntry } from "@/api/workflow"

export interface VariableSource {
  kind: "node" | "workflow_var"
  node_id: string
  label: string
  fields: Array<{ name: string; type: string }>
}


/**
 * Static-declared outputs (`manifest.io.outputs`) are only a *baseline*. Some
 * nodes emit fields that are only knowable from their DSL config:
 *
 *  - Start:          outputs ≈ declared `variables` + the implicit Workflow
 *                    Agent trigger fields (content / conversation_id / history / metadata).
 *                    If no variables declared, Start passes trigger through verbatim.
 *  - Variable Splitter: outputs = keys of `mapping`.
 *  - Variable Aggregator / Template / Code: stable; use manifest.
 *
 * This fn returns what a DOWNSTREAM picker should see, which is the union of
 * manifest outputs + config-derived dynamic outputs.
 */
function resolveNodeOutputs(
  nodeType: string,
  entry: NodeCatalogEntry | undefined,
  config: Record<string, unknown>,
): Array<{ name: string; type: string }> {
  const manifestOutputs = (entry?.io?.outputs ?? {}) as Record<string, { type?: string }>
  const base = Object.entries(manifestOutputs).map(([name, s]) => ({
    name,
    type: (s?.type as string) ?? "any",
  }))

  if (nodeType === "start") {
    // Declared variables (if any).
    const declared = ((config.variables as Array<{ name: string; type: string }> | undefined) ?? [])
      .filter((v) => v.name)
      .map((v) => ({ name: v.name, type: v.type ?? "any" }))

    // Implicit Workflow Agent trigger fields (spec 22 §1). We surface these
    // regardless of whether the workflow is bound to an agent — worst case
    // they're no-ops in manual-trigger workflows.
    const implicit: Array<{ name: string; type: string }> = [
      { name: "content", type: "string" },
      { name: "conversation_id", type: "string" },
      { name: "history", type: "array" },
      { name: "metadata", type: "object" },
    ]

    // Merge, declared takes precedence over implicit on name collisions.
    const byName = new Map<string, { name: string; type: string }>()
    for (const f of [...implicit, ...base, ...declared]) byName.set(f.name, f)
    return Array.from(byName.values())
  }

  if (nodeType === "variable-splitter") {
    const mapping = (config.mapping as Record<string, unknown> | undefined) ?? {}
    const dyn = Object.keys(mapping).map((k) => ({ name: k, type: "any" }))
    return dyn.length > 0 ? dyn : base
  }

  return base
}


export function computeUpstream(
  currentNodeId: string,
  nodes: Node[],
  edges: Edge[],
  catalog: NodeCatalogEntry[],
  workflowVariables: Array<{ name: string; type: string }>,
): VariableSource[] {
  const reverseAdj: Record<string, string[]> = {}
  for (const e of edges) {
    ;(reverseAdj[e.target] ??= []).push(e.source)
  }

  const visited = new Set<string>()
  const queue = [currentNodeId]
  while (queue.length > 0) {
    const id = queue.shift()!
    for (const pred of reverseAdj[id] ?? []) {
      if (!visited.has(pred)) {
        visited.add(pred)
        queue.push(pred)
      }
    }
  }

  const sources: VariableSource[] = []
  for (const id of Array.from(visited)) {
    const node = nodes.find((n) => n.id === id)
    if (!node) continue
    const data = (node.data ?? {}) as {
      nodeType?: string
      config?: Record<string, unknown>
    }
    const ntype = data.nodeType ?? "unknown"
    const entry = catalog.find((c) => c.manifest.type === ntype)
    const fields = resolveNodeOutputs(ntype, entry, data.config ?? {})
    sources.push({
      kind: "node",
      node_id: id,
      label: entry?.manifest.name ?? ntype,
      fields,
    })
  }

  // Workflow-level vars + implicit trigger blob (for non-Start references,
  // e.g. selecting `vars.trigger` as an object to pass into Code node).
  sources.push({
    kind: "workflow_var",
    node_id: "vars",
    label: "工作流变量",
    fields: [
      ...workflowVariables.map((v) => ({ name: v.name, type: v.type })),
      { name: "trigger", type: "object" },
    ],
  })

  return sources
}
