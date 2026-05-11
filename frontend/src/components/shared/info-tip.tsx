import type { ReactNode } from "react"
import { CircleHelp } from "lucide-react"
import { Tooltip } from "@douyinfe/semi-ui"

/**
 * 在术语旁加一个小问号图标，hover 显示通俗解释。
 * 让用户不用记专业术语也能看懂界面。
 *
 * 用法：
 *   <Label>BM25 权重 <InfoTip text="找词面一模一样的内容时给的权重" /></Label>
 */
export function InfoTip({
  text,
  className,
}: {
  text: ReactNode
  className?: string
}) {
  return (
    <Tooltip content={text} position="top">
      <span className={"inline-flex cursor-help align-middle " + (className ?? "")}>
        <CircleHelp className="size-3 text-muted-foreground" />
      </span>
    </Tooltip>
  )
}
