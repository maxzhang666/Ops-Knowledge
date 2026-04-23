import type { JSONContent } from "@tiptap/core"

const REF_RE = /\{\{#\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_.]+)\s*#\}\}/g

export function stringToDoc(text: string): JSONContent {
  const content: JSONContent[] = []
  let last = 0
  REF_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = REF_RE.exec(text)) !== null) {
    if (m.index > last) {
      content.push({ type: "text", text: text.slice(last, m.index) })
    }
    content.push({
      type: "variable",
      attrs: { node: m[1], path: m[2] },
    })
    last = m.index + m[0].length
  }
  if (last < text.length) {
    content.push({ type: "text", text: text.slice(last) })
  }
  return {
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: content.length > 0 ? content : undefined,
      },
    ],
  }
}

export function docToString(doc: JSONContent): string {
  let out = ""
  const walk = (node: JSONContent) => {
    if (node.type === "text") {
      out += node.text ?? ""
    } else if (node.type === "variable") {
      const attrs = (node.attrs ?? {}) as { node?: string; path?: string }
      if (attrs.node && attrs.path) out += `{{#${attrs.node}.${attrs.path}#}}`
    } else if (node.type === "paragraph") {
      if (node.content) node.content.forEach(walk)
      out += "\n"
    } else if (node.type === "hardBreak") {
      out += "\n"
    }
    // Ignore other node types.
  }
  if (doc.content) doc.content.forEach(walk)
  // Trim trailing newline inserted by the final paragraph.
  return out.replace(/\n$/, "")
}
