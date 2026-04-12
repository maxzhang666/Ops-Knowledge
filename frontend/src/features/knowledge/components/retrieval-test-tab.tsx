import { useState } from "react"
import { Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/shared/empty-state"
import { knowledgeApi, type RetrievalResult } from "@/api/knowledge"

interface RetrievalTestTabProps {
  kbId: string
}

export function RetrievalTestTab({ kbId }: RetrievalTestTabProps) {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<RetrievalResult[]>([])
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [tested, setTested] = useState(false)

  async function handleTest(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return

    setLoading(true)
    try {
      const res = await knowledgeApi.testRetrieval(kbId, { query: query.trim(), top_k: 5 })
      setResults(res.results)
      setElapsed(res.elapsed_ms)
      setTested(true)
    } finally {
      setLoading(false)
    }
  }

  function scoreColor(score: number): string {
    if (score >= 0.8) return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
    if (score >= 0.5) return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
    return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
  }

  return (
    <div className="mt-4 flex flex-col gap-4">
      <form onSubmit={handleTest} className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入检索查询..."
          className="max-w-md"
        />
        <Button type="submit" disabled={!query.trim() || loading}>
          <Search className="mr-1 size-4" />
          {loading ? "检索中..." : "测试"}
        </Button>
      </form>

      {elapsed !== null && (
        <p className="text-xs text-muted-foreground">
          耗时 {elapsed}ms，返回 {results.length} 条结果
        </p>
      )}

      {tested && results.length === 0 && (
        <EmptyState title="无匹配结果" description="尝试使用不同的查询语句" />
      )}

      {results.length > 0 && (
        <div className="flex flex-col gap-2">
          {results.map((r, i) => (
            <div key={i} className="rounded-lg border p-3">
              <div className="mb-2 flex items-center gap-2">
                <Badge variant="outline" className={`border-transparent ${scoreColor(r.score)}`}>
                  {(r.score * 100).toFixed(1)}%
                </Badge>
                <span className="text-xs text-muted-foreground">{r.document_name}</span>
              </div>
              <p className="line-clamp-4 text-sm">{r.chunk.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
