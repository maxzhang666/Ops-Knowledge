import { useEffect, useRef, useState } from "react"
import { Search, Send, Square } from "lucide-react"
import { MarkdownRender } from "@douyinfe/semi-ui"
import { markdownCodeBlockComponents } from "@/components/shared/markdown-code-block"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { EmptyState } from "@/components/shared/empty-state"
import { knowledgeApi, type RetrievalResult } from "@/api/knowledge"
import { modelApi, type RegistryEntry } from "@/api/model"

interface RetrievalTestTabProps {
  kbId: string
  kbIndexed: boolean  // whether the KB has any indexed chunks (from kb.chunk_count > 0)
}

export function RetrievalTestTab({ kbId, kbIndexed }: RetrievalTestTabProps) {
  return (
    <Tabs defaultValue="search" className="mt-4">
      <TabsList variant="line">
        <TabsTrigger value="search">检索结果</TabsTrigger>
        <TabsTrigger value="qa">快速问答</TabsTrigger>
      </TabsList>
      <TabsContent value="search" className="mt-4">
        <SearchPane kbId={kbId} />
      </TabsContent>
      <TabsContent value="qa" className="mt-4">
        <QAPane kbId={kbId} kbIndexed={kbIndexed} />
      </TabsContent>
    </Tabs>
  )
}

// ── Pane 1: raw retrieval ────────────────────────────────────────

function SearchPane({ kbId }: { kbId: string }) {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<RetrievalResult[]>([])
  const [timingMs, setTimingMs] = useState<number | null>(null)
  const [indexed, setIndexed] = useState<boolean>(true)
  const [loading, setLoading] = useState(false)
  const [tested, setTested] = useState(false)

  async function handleTest(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    try {
      const res = await knowledgeApi.testRetrieval(kbId, { query: query.trim(), top_k: 5 })
      setResults(res.results)
      setTimingMs(res.timing_ms)
      setIndexed(res.indexed)
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
    <div className="flex flex-col gap-4">
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

      {timingMs !== null && (
        <p className="text-xs text-muted-foreground">
          耗时 {timingMs}ms，返回 {results.length} 条结果
        </p>
      )}

      {tested && results.length === 0 && (
        indexed ? (
          <EmptyState title="无匹配结果" description="尝试使用不同的查询语句，或调整分片/检索参数" />
        ) : (
          <EmptyState
            title="该知识库尚未建立索引"
            description="请先在「文档」tab 上传并等待处理完成（状态变为已完成），随后即可检索"
          />
        )
      )}

      {results.length > 0 && (
        <div className="flex flex-col gap-2">
          {results.map((r, i) => (
            <div key={i} className="rounded-lg border p-3">
              <div className="mb-2 flex items-center gap-2">
                <Badge variant="outline" className={`border-transparent ${scoreColor(r.score)}`}>
                  {(r.score * 100).toFixed(1)}%
                </Badge>
                <span className="text-xs text-muted-foreground">{r.title}</span>
              </div>
              <p className="line-clamp-4 text-sm">{r.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Pane 2: quick Q&A (SSE) ──────────────────────────────────────

interface QAChunk {
  id: string
  content_preview: string
  score: number
  document_title: string
}

function QAPane({ kbId, kbIndexed }: { kbId: string; kbIndexed: boolean }) {
  const [llms, setLlms] = useState<RegistryEntry[]>([])
  const [modelId, setModelId] = useState<string>("")
  const [query, setQuery] = useState("")
  const [answer, setAnswer] = useState("")
  const [chunks, setChunks] = useState<QAChunk[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    (async () => {
      const reg = await modelApi.listRegistry({ model_type: "llm", enabled_only: "true" })
      const list = Array.isArray(reg) ? reg : []
      setLlms(list)
      if (list.length > 0 && !modelId) setModelId(list[0].id)
    })()
    return () => { abortRef.current?.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function stop() {
    abortRef.current?.abort()
    setStreaming(false)
  }

  async function ask(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim() || !modelId) return
    setStreaming(true)
    setAnswer("")
    setChunks([])
    setError(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      const token = localStorage.getItem("access_token")
      const res = await fetch(`/api/v1/knowledge/${kbId}/retrieval/qa`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token && { Authorization: `Bearer ${token}` }),
        },
        body: JSON.stringify({
          query: query.trim(),
          top_k: 5,
          model_registry_id: modelId,
        }),
        signal: ctrl.signal,
      })
      if (!res.ok || !res.body) {
        const detail = await res.text().catch(() => res.statusText)
        throw new Error(detail || "请求失败")
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        // Parse SSE frames: each ends with \n\n
        let idx: number
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const raw = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          processFrame(raw)
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError(err instanceof Error ? err.message : "发生错误")
      }
    } finally {
      setStreaming(false)
    }

    function processFrame(raw: string) {
      let ev = "message"
      let data = ""
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) ev = line.slice(6).trim()
        else if (line.startsWith("data:")) data += line.slice(5).trim()
      }
      if (!data) return
      try {
        const parsed = JSON.parse(data)
        if (ev === "retrieval_info") {
          setChunks(parsed.chunks || [])
        } else if (ev === "content_delta" && parsed.delta) {
          setAnswer((prev) => prev + parsed.delta)
        }
      } catch {
        // ignore malformed frames
      }
    }
  }

  if (!kbIndexed) {
    return (
      <EmptyState
        title="该知识库尚未建立索引"
        description="请先在「文档」tab 上传并等待处理完成（状态变为已完成），再使用快速问答"
      />
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={ask} className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">LLM 模型</label>
          <Select value={modelId || undefined} onValueChange={(v) => v && setModelId(v)}>
            <SelectTrigger className="w-64">
              {modelId
                ? <span className="truncate">
                    {(() => {
                      const m = llms.find((x) => x.id === modelId)
                      return m ? `${m.display_name || m.model_id} (${m.provider_name ?? ""})` : modelId
                    })()}
                  </span>
                : <SelectValue placeholder="选择 LLM" />}
            </SelectTrigger>
            <SelectContent>
              {llms.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.display_name || m.model_id} ({m.provider_name ?? ""})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="在当前知识库上提问..."
          className="max-w-md flex-1"
        />
        {streaming ? (
          <Button type="button" variant="outline" onClick={stop}>
            <Square className="mr-1 size-4" /> 停止
          </Button>
        ) : (
          <Button type="submit" disabled={!query.trim() || !modelId}>
            <Send className="mr-1 size-4" /> 提问
          </Button>
        )}
      </form>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {chunks.length > 0 && (
        <div className="rounded-lg border bg-muted/30 p-3">
          <p className="mb-2 text-xs font-medium text-muted-foreground">
            参考片段（{chunks.length}）
          </p>
          <ol className="flex flex-col gap-1.5 text-xs">
            {chunks.map((c, i) => (
              <li key={c.id}>
                <span className="mr-1.5 text-muted-foreground">[{i + 1}]</span>
                <span className="font-medium">{c.document_title}</span>
                <span className="ml-1.5 text-muted-foreground">
                  · {(c.score * 100).toFixed(0)}% · {c.content_preview}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {(answer || streaming) && (
        <div className="prose prose-sm max-w-none rounded-lg border p-4 dark:prose-invert">
          <MarkdownRender raw={answer || "..."} format="md" components={markdownCodeBlockComponents} />
          {streaming && (
            <span className="ml-1 inline-block h-3 w-1 animate-pulse bg-foreground" />
          )}
        </div>
      )}
    </div>
  )
}
