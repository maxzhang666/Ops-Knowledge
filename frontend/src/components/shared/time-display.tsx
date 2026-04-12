import dayjs from "dayjs"
import relativeTime from "dayjs/plugin/relativeTime"
import "dayjs/locale/zh-cn"

dayjs.extend(relativeTime)
dayjs.locale("zh-cn")

interface TimeDisplayProps {
  value: string
  className?: string
}

export function TimeDisplay({ value, className }: TimeDisplayProps) {
  const d = dayjs(value)
  const withinWeek = dayjs().diff(d, "day") < 7
  const display = withinWeek ? d.fromNow() : d.format("YYYY-MM-DD HH:mm")

  return (
    <time dateTime={value} title={d.format("YYYY-MM-DD HH:mm:ss")} className={className}>
      {display}
    </time>
  )
}
