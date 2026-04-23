import { useRef, useState } from "react"
import { Copy, Check } from "lucide-react"

/**
 * Semi `MarkdownRender` / `Chat` 的 `customMarkDownComponents.pre` 注入项。
 * 给代码块右上角挂一个仅 hover 时显示的复制按钮；行内 `<code>` 不动。
 */
function PreBlock(props: React.HTMLAttributes<HTMLPreElement>) {
  const ref = useRef<HTMLPreElement>(null)
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    const text = ref.current?.textContent ?? ""
    if (!text) return
    // navigator.clipboard 在非 HTTPS / 非 secure-context 下不可用；降级为 execCommand。
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).catch(() => fallbackCopy(text))
    } else {
      fallbackCopy(text)
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="group relative my-2">
      <pre ref={ref} {...props} />
      <button
        type="button"
        onClick={handleCopy}
        title={copied ? "已复制" : "复制代码"}
        className="absolute right-2 top-2 flex items-center gap-1 rounded bg-background/80 px-1.5 py-0.5 text-[10px] text-muted-foreground opacity-0 shadow-sm backdrop-blur transition group-hover:opacity-100 hover:text-foreground"
      >
        {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
        {copied ? "已复制" : "复制"}
      </button>
    </div>
  )
}

function fallbackCopy(text: string): void {
  const ta = document.createElement("textarea")
  ta.value = text
  ta.style.position = "fixed"
  ta.style.left = "-9999px"
  document.body.appendChild(ta)
  ta.select()
  try {
    document.execCommand("copy")
  } finally {
    document.body.removeChild(ta)
  }
}

/**
 * 喂给 `MarkdownRender` 或 `<Chat customMarkDownComponents={...}>` 的组件映射。
 * 使用处若还要叠加自定义 sup 等，展开合并即可。
 */
export const markdownCodeBlockComponents = {
  pre: PreBlock,
} as const
