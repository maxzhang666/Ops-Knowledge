import { NodeViewWrapper, type NodeViewProps } from "@tiptap/react"

export function VariableChip({ node }: NodeViewProps) {
  const { node: n, path } = node.attrs as { node: string; path: string }
  return (
    <NodeViewWrapper
      as="span"
      className="mx-0.5 inline-flex select-none items-center rounded bg-primary/15 px-1.5 py-0.5 align-baseline text-xs font-medium text-primary"
    >
      {n}.{path}
    </NodeViewWrapper>
  )
}
