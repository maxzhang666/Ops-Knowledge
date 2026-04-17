// Semi UI 2.84+ auto-injects its CSS via the library's index.js
// (see '@douyinfe/semi-ui/lib/es/index.js' line 1: `import './_base/base.css'`).
// No manual CSS import needed. Semi uses the `--semi-*` namespace, so it does
// not collide with shadcn's `--primary/--background/...` tokens. See
// 08-frontend-design.md §Chat (Semi).
import { MarkdownRender } from "@douyinfe/semi-ui"
import { useMemo } from "react"

import { cn } from "@/lib/utils"
import type { Message } from "@/api/chat"

interface MessageBubbleProps {
  message: Message
  onCitationClick?: (index: number) => void
}

/**
 * Replace ``[N]`` citation tokens with inline HTML ``<sup>`` tags. Markdown
 * renderers typically preserve inline HTML; if Semi strips it we'd need to
 * switch to the `components` prop, but for Phase 2 POC this works.
 */
function injectCitations(content: string): string {
  return content.replace(
    /\[(\d+)\]/g,
    (_, n) =>
      `<sup class="citation-ref" data-cite="${n}" role="button" tabindex="0">[${n}]</sup>`,
  )
}

export function MessageBubble({ message, onCitationClick }: MessageBubbleProps) {
  const isUser = message.role === "user"
  // Assistant content is rendered as Markdown; user content kept as plain text
  // to avoid parsing user-typed markdown-like syntax unexpectedly.
  const processed = useMemo(
    () => (isUser ? message.content : injectCitations(message.content)),
    [isUser, message.content],
  )

  function handleClick(e: React.MouseEvent<HTMLDivElement>) {
    if (!onCitationClick) return
    const target = e.target as HTMLElement
    const sup = target.closest<HTMLElement>(".citation-ref")
    if (!sup) return
    const idx = Number(sup.dataset.cite)
    if (!Number.isNaN(idx)) onCitationClick(idx)
  }

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "whitespace-pre-wrap bg-primary text-primary-foreground"
            : "bg-muted text-foreground chat-markdown-bubble",
        )}
        onClick={handleClick}
      >
        {isUser ? (
          message.content
        ) : (
          <MarkdownRender raw={processed} format="md" />
        )}
      </div>
    </div>
  )
}
