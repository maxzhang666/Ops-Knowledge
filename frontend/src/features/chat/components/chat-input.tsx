import { useRef, useState } from "react"
import { Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

const MAX_CHARS = 4000

interface ChatInputProps {
  onSend: (content: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)

  function handleSend() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue("")
    ref.current?.focus()
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="border-t bg-background p-4">
      <div className="relative">
        <Textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value.slice(0, MAX_CHARS))}
          onKeyDown={handleKeyDown}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          rows={3}
          className="resize-none pr-12"
          disabled={disabled}
        />
        <Button
          size="icon"
          className="absolute right-2 bottom-2"
          onClick={handleSend}
          disabled={!value.trim() || disabled}
        >
          <Send className="size-4" />
        </Button>
      </div>
      <div className="mt-1 text-right text-xs text-muted-foreground">
        {value.length}/{MAX_CHARS}
      </div>
    </div>
  )
}
