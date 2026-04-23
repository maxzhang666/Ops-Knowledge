import { useCallback, useEffect, useMemo, useState } from "react"
import { createPortal } from "react-dom"
import { EditorContent, useEditor, type Editor } from "@tiptap/react"
import StarterKit from "@tiptap/starter-kit"
import { Variable } from "./variable-node"
import { computeUpstream } from "./upstream"
import { VariablePicker } from "./picker"
import { docToString, stringToDoc } from "./serialize"
import { useEditorStore } from "../store"

interface Props {
  value: string
  onChange: (v: string) => void
  currentNodeId: string
  placeholder?: string
}


export function VariableEditor({ value, onChange, currentNodeId, placeholder }: Props) {
  const nodes = useEditorStore((s) => s.nodes)
  const edges = useEditorStore((s) => s.edges)
  const catalog = useEditorStore((s) => s.catalog)
  const wfVars = useMemo(() => [] as Array<{ name: string; type: string }>, [])

  const sources = useMemo(
    () => computeUpstream(currentNodeId, nodes, edges, catalog, wfVars),
    [currentNodeId, nodes, edges, catalog, wfVars],
  )

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        codeBlock: false,
      }),
      Variable,
    ],
    content: stringToDoc(value),
    onUpdate: ({ editor }) => {
      onChange(docToString(editor.getJSON()))
    },
    editorProps: {
      attributes: {
        class:
          "prose prose-sm dark:prose-invert max-w-none rounded-md border border-input bg-background px-3 py-2 min-h-[6rem] focus:outline-none focus:ring-2 focus:ring-ring",
        "data-placeholder": placeholder ?? "",
      },
    },
  })

  // External value changes (different node selected) → reset content.
  useEffect(() => {
    if (!editor) return
    const current = docToString(editor.getJSON())
    if (current !== value) {
      editor.commands.setContent(stringToDoc(value))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor, value])

  const [picker, setPicker] = useState<{ top: number; left: number } | null>(null)

  useEffect(() => {
    if (!editor) return
    const handler = (ev: KeyboardEvent) => {
      if (!editor.isFocused) return
      const trigger = ev.key === "/" || (ev.key === "{" && prevCharIs(editor, "{"))
      if (!trigger) return
      const sel = editor.state.selection
      const coords = editor.view.coordsAtPos(sel.from)
      setPicker({ top: coords.bottom + 4, left: coords.left })
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [editor])

  const insertVariable = useCallback(
    (nodeId: string, field: string) => {
      if (!editor) return
      editor
        .chain()
        .focus()
        .insertContent({ type: "variable", attrs: { node: nodeId, path: field } })
        .run()
      setPicker(null)
    },
    [editor],
  )

  return (
    <div className="relative">
      <EditorContent editor={editor} />
      {picker &&
        createPortal(
          <VariablePicker
            sources={sources}
            position={picker}
            onPick={insertVariable}
            onClose={() => setPicker(null)}
          />,
          document.body,
        )}
    </div>
  )
}


function prevCharIs(editor: Editor, ch: string): boolean {
  const { from } = editor.state.selection
  if (from === 0) return false
  const prev = editor.state.doc.textBetween(Math.max(0, from - 1), from, "\n")
  return prev === ch
}
