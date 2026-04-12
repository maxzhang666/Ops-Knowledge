import { cn } from "@/lib/utils"
import type { Message } from "@/api/chat"

interface MessageBubbleProps {
  message: Message
  onCitationClick?: (index: number) => void
}

function renderContent(content: string, onCitationClick?: (index: number) => void) {
  const parts = content.split(/(\[\d+\])/)
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/)
    if (match && onCitationClick) {
      const idx = parseInt(match[1], 10)
      return (
        <button
          key={i}
          className="mx-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary/10 text-[10px] font-medium text-primary hover:bg-primary/20"
          onClick={() => onCitationClick(idx)}
        >
          {idx}
        </button>
      )
    }
    return <span key={i}>{part}</span>
  })
}

export function MessageBubble({ message, onCitationClick }: MessageBubbleProps) {
  const isUser = message.role === "user"

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
        )}
      >
        {renderContent(message.content, onCitationClick)}
      </div>
    </div>
  )
}
