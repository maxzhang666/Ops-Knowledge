import type { ProcessingProgress as ProgressData } from "@/api/knowledge"

const stageLabels: Record<string, string> = {
  downloading: "下载中",
  parsing: "解析中",
  chunking: "切片中",
  indexing: "建立索引",
  completed: "已完成",
}

interface ProcessingProgressProps {
  progress: ProgressData
}

export function ProcessingProgress({ progress }: ProcessingProgressProps) {
  const pct = progress.total > 0
    ? Math.round((progress.completed / progress.total) * 100)
    : 0
  const label = stageLabels[progress.stage] ?? progress.stage

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {progress.completed}/{progress.total}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
