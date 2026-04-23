import { useEffect, useState } from "react"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"


/**
 * HTTP Request `body` accepts any JSON shape or plain string. The raw type
 * is `any` in the schema, so we give users a JSON textarea with live parse
 * feedback — invalid JSON stays in the editor as a string (the node accepts
 * that too and passes as raw body).
 */
export function JsonBodyEditor({
  value,
  onChange,
}: {
  value: unknown
  onChange: (v: unknown) => void
}) {
  const [text, setText] = useState(() => stringify(value))
  const [err, setErr] = useState<string | null>(null)

  // Sync when the selected node changes externally.
  useEffect(() => {
    setText(stringify(value))
    setErr(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleChange(next: string) {
    setText(next)
    if (next.trim() === "") {
      setErr(null)
      onChange(undefined)
      return
    }
    try {
      const parsed = JSON.parse(next)
      setErr(null)
      onChange(parsed)
    } catch (e) {
      // Keep the text-as-string as the live value so the user can still see
      // what they typed; emit as string so backend receives the literal.
      setErr(e instanceof Error ? e.message : String(e))
      onChange(next)
    }
  }

  return (
    <div className="space-y-1">
      <Textarea
        rows={6}
        value={text}
        onChange={(e) => handleChange(e.target.value)}
        placeholder='JSON 对象，例如 {"foo": "bar"}，或纯文本'
        className="font-mono text-[11px]"
      />
      {err && (
        <Label className="text-xs text-destructive">JSON 解析失败：{err}</Label>
      )}
    </div>
  )
}


function stringify(v: unknown): string {
  if (v === undefined || v === null) return ""
  if (typeof v === "string") return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}
