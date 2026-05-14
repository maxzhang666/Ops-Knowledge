import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Search, Send, Square, FileText, Clock, History, Filter,
  ThumbsUp, ThumbsDown, BookmarkPlus,
  Crosshair, Sparkles, Cpu,
} from "lucide-react"
import {
  MarkdownRender, Button, Input, InputNumber, Select, Switch, Tag, Spin,
  Collapse, Empty, Slider, Modal, Toast,
} from "@douyinfe/semi-ui"
import { markdownCodeBlockComponents } from "@/components/shared/markdown-code-block"
import {
  knowledgeApi,
  type RetrievalResult,
  type RetrievalLogItem,
  type GovernanceHealth,
} from "@/api/knowledge"
import { modelApi, type RegistryEntry } from "@/api/model"
import { tagDictionaryApi } from "@/api/tag_dictionary"
import { InfoTip } from "@/components/shared/info-tip"

interface RetrievalTestTabProps {
  kbId: string
  kbIndexed: boolean
}

// ─── Param panel state shape ─────────────────────────────────────

interface SearchParams {
  top_k: number
  bm25_weight: number
  vector_weight: number
  score_threshold: number  // 0 = disabled
  rerank_enabled: boolean
  rerank_registry_id: string  // M6.8 — empty = use KB default reranker
  embedding_registry_id: string  // empty = use KB default
  // Spec 25 L2 — chunks.chunk_tags 过滤（三键各自数组，AND 串联）
  tag_any_of: string[]
  tag_all_of: string[]
  tag_not: string[]
}

const DEFAULT_PARAMS: SearchParams = {
  top_k: 5,
  bm25_weight: 1.0,
  vector_weight: 1.0,
  score_threshold: 0,
  rerank_enabled: false,
  rerank_registry_id: "",
  embedding_registry_id: "",
  tag_any_of: [],
  tag_all_of: [],
  tag_not: [],
}

interface RecommendationPayload {
  bm25_weight: number
  vector_weight: number
  top_k: number
  rerank: boolean
  note: string
}

interface RecommendationRow {
  query_type: string
  sample_size: number
  payload: {
    base: RecommendationPayload
    tuned: RecommendationPayload
    note: string
  }
  generated_at: string
}

// ─── Root ────────────────────────────────────────────────────────
//
// M5 merged the former "快速问答" pane into SearchWorkbench: there's now
// a single page that does both retrieval debugging and (on demand) RAG
// answer generation, sharing one query + one set of params + history.
// QAPane is gone.

export function RetrievalTestTab({ kbId, kbIndexed }: RetrievalTestTabProps) {
  return (
    <div className="mt-4">
      <SearchWorkbench kbId={kbId} kbIndexed={kbIndexed} />
    </div>
  )
}

// ─── Search Workbench (3-column) ─────────────────────────────────

function SearchWorkbench({ kbId, kbIndexed }: { kbId: string; kbIndexed: boolean }) {
  const [query, setQuery] = useState("")
  const [params, setParams] = useState<SearchParams>(DEFAULT_PARAMS)
  const [results, setResults] = useState<RetrievalResult[]>([])
  const [queryUsed, setQueryUsed] = useState<string>("")
  const [timingMs, setTimingMs] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [tested, setTested] = useState(false)

  const [history, setHistory] = useState<RetrievalLogItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyEmptyOnly, setHistoryEmptyOnly] = useState(false)
  const [historyMineOnly, setHistoryMineOnly] = useState(false)
  const [activeLogId, setActiveLogId] = useState<string | null>(null)

  const [embeddingOptions, setEmbeddingOptions] = useState<RegistryEntry[]>([])
  // M6.8 — reranker model registry list for the rerank-enabled section
  const [rerankerOptions, setRerankerOptions] = useState<RegistryEntry[]>([])
  // Spec 25 — KB 字典 canonical 列表，供 tag filter multi-select 联想
  const [tagOptions, setTagOptions] = useState<string[]>([])
  useEffect(() => {
    modelApi.listRegistry({ model_type: "reranker", enabled_only: "true" })
      .then((list) => setRerankerOptions(Array.isArray(list) ? list : []))
      .catch(() => setRerankerOptions([]))
  }, [])
  useEffect(() => {
    tagDictionaryApi.list(kbId, { page_size: 200 })
      .then((r) => setTagOptions(r.items.map((it) => it.canonical)))
      .catch(() => setTagOptions([]))
  }, [kbId])

  // M3 — feedback bookkeeping: chunk_id → "up" | "down" | undefined.
  // Reset whenever a different result set is rendered so we don't carry
  // stale votes across runs (a 👍 on chunk A in run 1 isn't a 👍 in run 2).
  const [feedback, setFeedback] = useState<Record<string, "up" | "down">>({})
  useEffect(() => { setFeedback({}) }, [results])

  // M3 — Golden Dataset modal state
  const [addToDatasetOpen, setAddToDatasetOpen] = useState(false)

  // M5 — RAG answer generation. The LLM dropdown lives in ParamsPanel; the
  // "+生成答案" button only appears once retrieval has produced chunks.
  const [llmOptions, setLlmOptions] = useState<RegistryEntry[]>([])
  const [llmId, setLlmId] = useState<string>("")
  useEffect(() => {
    modelApi.listRegistry({ model_type: "llm", enabled_only: "true" })
      .then((list) => {
        const arr = Array.isArray(list) ? list : []
        setLlmOptions(arr)
        if (arr.length > 0) setLlmId(arr[0].id)
      })
      .catch(() => setLlmOptions([]))
  }, [])

  const [answer, setAnswer] = useState("")
  const [answerStreaming, setAnswerStreaming] = useState(false)
  const [answerMeta, setAnswerMeta] = useState<{
    model: string | null
    tokens: { prompt: number; completion: number; total: number } | null
    cost_usd: number | null
  } | null>(null)
  const [answerError, setAnswerError] = useState<string | null>(null)
  const answerAbortRef = useRef<AbortController | null>(null)
  useEffect(() => () => { answerAbortRef.current?.abort() }, [])

  function stopAnswer() {
    answerAbortRef.current?.abort()
    setAnswerStreaming(false)
  }

  async function generateAnswer() {
    if (!query.trim() || !llmId) return
    setAnswerStreaming(true)
    setAnswer("")
    setAnswerMeta(null)
    setAnswerError(null)
    const ctrl = new AbortController()
    answerAbortRef.current = ctrl
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
          top_k: params.top_k,
          model_registry_id: llmId,
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
        let idx: number
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const raw = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          let ev = "message"
          let dataStr = ""
          for (const line of raw.split("\n")) {
            if (line.startsWith("event:")) ev = line.slice(6).trim()
            else if (line.startsWith("data:")) dataStr += line.slice(5).trim()
          }
          if (!dataStr) continue
          try {
            const parsed = JSON.parse(dataStr)
            if (ev === "content_delta" && parsed.delta) {
              setAnswer((prev) => prev + parsed.delta)
            } else if (ev === "message_end") {
              setAnswerMeta({
                model: parsed.model ?? null,
                tokens: parsed.tokens ?? null,
                cost_usd: parsed.cost_usd ?? null,
              })
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setAnswerError(err instanceof Error ? err.message : "生成失败")
      }
    } finally {
      setAnswerStreaming(false)
    }
  }

  // Reset answer state whenever the result set changes (new search /
  // history replay) — old answer is no longer pinned to the visible chunks.
  useEffect(() => {
    setAnswer("")
    setAnswerMeta(null)
    setAnswerError(null)
  }, [results])

  // M4.3 — compare-mode: pick 2+ history items to diff their hit lists.
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set())
  const [compareOpen, setCompareOpen] = useState(false)
  function toggleCompare(logId: string) {
    setCompareIds((prev) => {
      const next = new Set(prev)
      if (next.has(logId)) next.delete(logId)
      else if (next.size < 2) next.add(logId)  // cap at 2 for now (side-by-side)
      else {
        Toast.info("最多对比 2 条历史；取消勾选其中一条后再选")
      }
      return next
    })
  }

  // M4.1 — KB health snapshot for the top status bar
  const [health, setHealth] = useState<GovernanceHealth | null>(null)
  // KB headline counts — denormalised on `knowledge_bases`. Shown alongside
  // facet scores so users can tell "55 chunks" (count) apart from
  // "Chunk 质量 75 分" (score).
  const [kbCounts, setKbCounts] = useState<{ chunk_count: number; document_count: number } | null>(null)
  useEffect(() => {
    knowledgeApi.governance(kbId)
      .then(setHealth)
      .catch(() => setHealth(null))
    knowledgeApi.getKB(kbId)
      .then((kb) => setKbCounts({
        chunk_count: kb.chunk_count ?? 0,
        document_count: kb.document_count ?? 0,
      }))
      .catch(() => setKbCounts(null))
  }, [kbId])

  // M4.2 — retrieval auto-tuning recommendations (Plan 35).
  // Cached at mount; one-click apply fills the params panel.
  const [recommendations, setRecommendations] = useState<RecommendationRow[]>([])
  useEffect(() => {
    knowledgeApi.retrievalRecommendations(kbId)
      .then((list) => setRecommendations(list as unknown as RecommendationRow[]))
      .catch(() => setRecommendations([]))
  }, [kbId])

  // M6.3 — 阈值建议：baseline floor 算法（抽 chunk pairwise cosine P95）
  const [thresholdSuggestion, setThresholdSuggestion] = useState<
    { sample_size: number; floor: number | null; recommended: number | null } | null
  >(null)
  const refreshThresholdSuggestion = () => {
    knowledgeApi.retrievalThresholdSuggestion(kbId)
      .then((res) =>
        setThresholdSuggestion({
          sample_size: res.sample_size,
          floor: res.floor,
          recommended: res.recommended,
        }),
      )
      .catch(() => setThresholdSuggestion(null))
  }
  useEffect(() => {
    refreshThresholdSuggestion()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId])

  function applyRecommendation(r: RecommendationRow) {
    // Use tuned values when sample is meaningful (sample_size >= 10), else
    // fall back to baseline. This matches the Plan 35 recommender's own
    // fallback logic.
    const usable = r.sample_size >= 10 ? r.payload.tuned : r.payload.base
    setParams((prev) => ({
      ...prev,
      top_k: usable.top_k,
      bm25_weight: usable.bm25_weight,
      vector_weight: usable.vector_weight,
      rerank_enabled: usable.rerank,
    }))
    Toast.success(`已应用 ${r.query_type} 推荐参数`)
  }

  // M4.4 — persist current params as the KB's default retrieval_config.
  // Merge into the existing config (preserving rerank model bindings the
  // user set elsewhere) instead of overwriting the whole blob.
  const [savingDefaults, setSavingDefaults] = useState(false)
  async function saveAsKBDefault() {
    setSavingDefaults(true)
    try {
      const kb = await knowledgeApi.getKB(kbId)
      const merged = {
        ...(kb.retrieval_config || {}),
        top_k: params.top_k,
        bm25_weight: params.bm25_weight,
        vector_weight: params.vector_weight,
        score_threshold: params.score_threshold > 0 ? params.score_threshold : undefined,
      }
      await knowledgeApi.updateKB(kbId, { retrieval_config: merged })
      Toast.success("当前参数已设为知识库默认")
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSavingDefaults(false)
    }
  }

  const reloadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const list = await knowledgeApi.listRetrievalLogs(kbId, {
        limit: 50,
        empty: historyEmptyOnly || undefined,
        mine: historyMineOnly || undefined,
      })
      setHistory(list)
    } finally {
      setHistoryLoading(false)
    }
  }, [kbId, historyEmptyOnly, historyMineOnly])

  useEffect(() => { reloadHistory() }, [reloadHistory])

  useEffect(() => {
    (async () => {
      try {
        const list = await modelApi.listRegistry({ model_type: "embedding", enabled_only: "true" })
        setEmbeddingOptions(Array.isArray(list) ? list : [])
      } catch { /* no-op */ }
    })()
  }, [])

  async function runSearch() {
    if (!query.trim()) return
    setLoading(true)
    try {
      // Spec 25 L2 — tag_filter 仅在有任一非空数组时透传，避免空 dict 引发后端 noop
      const tagFilter = (
        params.tag_any_of.length || params.tag_all_of.length || params.tag_not.length
      ) ? {
        any_of: params.tag_any_of.length ? params.tag_any_of : undefined,
        all_of: params.tag_all_of.length ? params.tag_all_of : undefined,
        not: params.tag_not.length ? params.tag_not : undefined,
      } : undefined
      const res = await knowledgeApi.testRetrieval(kbId, {
        query: query.trim(),
        top_k: params.top_k,
        bm25_weight: params.bm25_weight,
        vector_weight: params.vector_weight,
        score_threshold: params.score_threshold > 0 ? params.score_threshold : undefined,
        rerank_enabled: params.rerank_enabled || undefined,
        rerank_registry_id:
          params.rerank_enabled && params.rerank_registry_id
            ? params.rerank_registry_id
            : undefined,
        embedding_registry_id: params.embedding_registry_id || undefined,
        tag_filter: tagFilter,
      })
      setResults(res.results)
      setQueryUsed(res.query_used)
      setTimingMs(res.timing_ms)
      setTested(true)
      setActiveLogId(null)  // current is fresh, not a replay
      reloadHistory()
      refreshThresholdSuggestion()  // 新 log 写入后刷新建议（采样会增长）
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "检索失败")
    } finally {
      setLoading(false)
    }
  }

  async function handleFeedback(chunkId: string, sentiment: "up" | "down") {
    // Toggle: clicking the same vote again retracts it (sentiment=0).
    const current = feedback[chunkId]
    const isRetract = current === sentiment
    const next = isRetract ? 0 : sentiment === "up" ? 1 : -1
    try {
      await knowledgeApi.retrievalFeedback(kbId, {
        chunk_id: chunkId,
        sentiment: next as -1 | 0 | 1,
        log_id: activeLogId ?? undefined,
      })
      setFeedback((prev) => {
        const copy = { ...prev }
        if (isRetract) delete copy[chunkId]
        else copy[chunkId] = sentiment
        return copy
      })
      Toast.success(isRetract ? "已撤销反馈" : sentiment === "up" ? "已标记为相关" : "已标记为不相关")
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "反馈失败")
    }
  }

  async function replayLog(log: RetrievalLogItem) {
    // Fill query + params back to the form so the user can iterate
    setQuery(log.query)
    setActiveLogId(log.id)
    if (log.params) {
      const p = log.params as Record<string, unknown>
      const tf = (p.tag_filter as Record<string, unknown> | undefined) ?? {}
      setParams({
        top_k: (p.top_k as number) ?? DEFAULT_PARAMS.top_k,
        bm25_weight: (p.bm25_weight as number) ?? DEFAULT_PARAMS.bm25_weight,
        vector_weight: (p.vector_weight as number) ?? DEFAULT_PARAMS.vector_weight,
        score_threshold: (p.score_threshold as number) ?? 0,
        rerank_enabled: Boolean(p.rerank_enabled),
        rerank_registry_id: (p.rerank_registry_id as string) ?? "",
        embedding_registry_id: (p.embedding_registry_id as string) ?? "",
        tag_any_of: Array.isArray(tf.any_of) ? (tf.any_of as string[]) : [],
        tag_all_of: Array.isArray(tf.all_of) ? (tf.all_of as string[]) : [],
        tag_not: Array.isArray(tf.not) ? (tf.not as string[]) : [],
      })
    }
    // Pull the snapshot of the hit list captured at retrieval time, NOT
    // re-run the pipeline. This survives chunk reprocessing / index drift.
    setLoading(true)
    try {
      const detail = await knowledgeApi.getRetrievalLog(kbId, log.id)
      setResults(detail.results)
      setQueryUsed(detail.query)
      setTimingMs(detail.latency_ms ?? null)
      setTested(true)
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "加载历史快照失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    // Cap workbench width on large displays — 1400px is wide enough for the
    // history sidebar + chunk cards + score breakdown without leaving long
    // text running edge to edge. mx-auto centres it in viewports beyond
    // that. Smaller screens are unaffected (max-w only kicks in past the
    // breakpoint).
    <div className="mx-auto grid max-w-[1400px] grid-cols-12 gap-4">
      {/* ── KB health bar (M4.1) ── */}
      {health && (
        <div className="col-span-12">
          <KBHealthBar health={health} counts={kbCounts} />
        </div>
      )}

      {/* ── Top: query + params (full width) ── */}
      <div className="col-span-12 flex flex-col gap-3">
        <div className="flex gap-2">
          <Input
            value={query}
            onChange={setQuery}
            placeholder="输入检索查询，回车或点击「检索」"
            onKeyDown={(e) => { if (e.key === "Enter" && !loading) runSearch() }}
          />
          <Button
            theme="solid"
            type="primary"
            icon={<Search className="size-4" />}
            onClick={runSearch}
            loading={loading}
            disabled={!query.trim()}
          >
            检索
          </Button>
        </div>

        <Collapse keepDOM>
          <Collapse.Panel
            header="检索参数"
            itemKey="params"
            extra={<ParamsSummary p={params} />}
          >
            <ParamsPanel
              value={params}
              onChange={setParams}
              embeddingOptions={embeddingOptions}
              rerankerOptions={rerankerOptions}
              tagOptions={tagOptions}
              llmOptions={llmOptions}
              llmId={llmId}
              onLlmChange={setLlmId}
              recommendations={recommendations}
              onApplyRecommendation={applyRecommendation}
              thresholdSuggestion={thresholdSuggestion}
              onSaveAsDefault={saveAsKBDefault}
              savingDefault={savingDefaults}
            />
          </Collapse.Panel>
        </Collapse>
      </div>

      {/* ── Left: history sidebar ── */}
      <div className="col-span-3 flex flex-col gap-2">
        <div className="flex items-center gap-1.5">
          <History className="size-3.5 text-muted-foreground" />
          <span className="text-sm font-medium">历史</span>
          <span className="text-xs text-muted-foreground">({history.length})</span>
          {historyLoading && <Spin size="small" />}
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={historyEmptyOnly}
              onChange={(e) => setHistoryEmptyOnly(e.target.checked)}
            />
            <Filter className="size-3" /> 召回为 0
          </label>
          <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={historyMineOnly}
              onChange={(e) => setHistoryMineOnly(e.target.checked)}
            />
            仅我的
          </label>
        </div>
        {compareIds.size >= 2 && (
          <Button
            theme="light"
            type="primary"
            size="small"
            onClick={() => setCompareOpen(true)}
          >
            对比已选 {compareIds.size} 项
          </Button>
        )}
        <div className="flex max-h-[640px] flex-col gap-1 overflow-y-auto">
          {history.length === 0 ? (
            <Empty description="暂无历史" />
          ) : (
            history.map((h) => (
              <HistoryItem
                key={h.id}
                log={h}
                active={activeLogId === h.id}
                checked={compareIds.has(h.id)}
                onClick={() => replayLog(h)}
                onToggleCompare={() => toggleCompare(h.id)}
              />
            ))
          )}
        </div>
      </div>

      {/* ── Right: results ── */}
      <div className="col-span-9 flex flex-col gap-3">
        {!kbIndexed && (
          <Empty
            title="该知识库尚未建立索引"
            description="请先在「文档」tab 上传并等待处理完成，再进行检索测试"
          />
        )}

        {kbIndexed && tested && timingMs !== null && (
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {activeLogId && <Tag size="small" color="blue">历史快照</Tag>}
            <span>
              <Clock className="mr-0.5 inline size-3" />
              {activeLogId ? "原耗时" : "耗时"} {timingMs}ms
            </span>
            <span>·</span>
            <span>召回 {results.length}</span>
            {queryUsed !== query.trim() && (
              <>
                <span>·</span>
                <span>实际查询: <span className="font-mono">{queryUsed}</span></span>
              </>
            )}
            {results.length > 0 && (
              <div className="ml-auto flex items-center gap-1">
                {answerStreaming ? (
                  <Button
                    theme="borderless"
                    size="small"
                    icon={<Square className="size-3.5" />}
                    onClick={stopAnswer}
                  >
                    停止生成
                  </Button>
                ) : (
                  <Button
                    theme="borderless"
                    size="small"
                    icon={<Send className="size-3.5" />}
                    onClick={generateAnswer}
                    disabled={!llmId}
                    title={llmId ? "" : "未配置可用 LLM —— 请到模型管理添加并启用一个 LLM"}
                  >
                    生成答案
                  </Button>
                )}
                <Button
                  theme="borderless"
                  size="small"
                  icon={<BookmarkPlus className="size-3.5" />}
                  onClick={() => setAddToDatasetOpen(true)}
                >
                  加入测试集
                </Button>
              </div>
            )}
          </div>
        )}

        {kbIndexed && tested && results.length === 0 && (
          <Empty title="无匹配结果" description="尝试不同查询，或调低「最低向量相关度」、调整 BM25/向量权重" />
        )}

        {/* M6.3 — 弱召回告警：三信号 OR 判定，命中任一即提示 */}
        {(() => {
          if (results.length === 0) return null
          const denses = results
            .map((r) => r.dense_score)
            .filter((v): v is number => typeof v === "number")
          const allBelow06 = denses.length > 0 && denses.every((d) => d < 0.6)
          const allBm25Null = results.every((r) => r.bm25_score == null)
          const denseSpread =
            denses.length > 1
              ? Math.max(...denses) - Math.min(...denses)
              : Infinity
          const narrowSpread = denses.length >= 3 && denseSpread < 0.05
          if (!allBelow06 && !allBm25Null && !narrowSpread) return null

          const reasons: string[] = []
          if (allBelow06) reasons.push("所有结果 dense<0.6")
          if (allBm25Null) reasons.push("BM25 全空（仅向量命中，词面 0 重叠）")
          if (narrowSpread)
            reasons.push(`dense 跨度仅 ${denseSpread.toFixed(3)}（结果挤在 floor 附近）`)

          return (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-2.5 text-xs text-amber-800">
              <div className="flex items-center gap-1 font-medium">
                <span>疑似弱召回，回答可能不准确</span>
                <InfoTip text="「召回」是检索领域术语，指「从知识库捞出的候选结果集合」。「弱召回」= 候选结果整体质量低，即使有结果也可能跟你的查询不真正相关。系统通过三个信号判定：所有结果语义分 < 0.6 / 全没字面命中 / 语义分跨度太小（结果挤在模型 floor 附近无差别）。继续让 AI 基于这些内容回答，容易胡编" />
              </div>
              <div className="mt-0.5 text-amber-700">
                命中信号：{reasons.join(" · ")}
              </div>
              <div className="mt-0.5 text-amber-700">
                建议：(1) 换种说法重试；(2) 检查知识库是否覆盖此话题；
                (3) 提高「最低向量相关度」到模型 floor 之上
              </div>
            </div>
          )
        })()}

        {(answer || answerStreaming || answerError) && (
          <AnswerCard
            answer={answer}
            streaming={answerStreaming}
            meta={answerMeta}
            error={answerError}
          />
        )}

        {results.length > 0 && (
          <div className="flex flex-col gap-2">
            {results.map((r, i) => (
              <ChunkCard
                key={r.chunk_id}
                index={i + 1}
                result={r}
                feedback={feedback[r.chunk_id]}
                onFeedback={(s) => handleFeedback(r.chunk_id, s)}
              />
            ))}
          </div>
        )}
      </div>

      <AddToDatasetModal
        open={addToDatasetOpen}
        onClose={() => setAddToDatasetOpen(false)}
        kbId={kbId}
        query={queryUsed || query.trim()}
        chunkIds={results.map((r) => r.chunk_id)}
      />

      <CompareModal
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        kbId={kbId}
        logIds={Array.from(compareIds)}
      />
    </div>
  )
}

// ─── M4.3 — Side-by-side compare modal ───────────────────────────

function CompareModal({
  open, onClose, kbId, logIds,
}: {
  open: boolean
  onClose: () => void
  kbId: string
  logIds: string[]
}) {
  const [details, setDetails] = useState<RetrievalLogDetailLite[] | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || logIds.length !== 2) return
    setLoading(true)
    Promise.all(logIds.map((id) => knowledgeApi.getRetrievalLog(kbId, id)))
      .then((rows) => setDetails(rows.map((r) => ({
        id: r.id,
        query: r.query,
        params: r.params,
        latency_ms: r.latency_ms,
        results: r.results,
      }))))
      .catch((err) => {
        setDetails(null)
        Toast.error(err instanceof Error ? err.message : "加载对比数据失败")
      })
      .finally(() => setLoading(false))
  }, [open, kbId, logIds.join("|")])  // eslint-disable-line react-hooks/exhaustive-deps

  // Compute set diff: chunk_id → A only / B only / both
  const diffMap = useMemo(() => {
    const m = new Map<string, "A" | "B" | "both">()
    if (!details || details.length !== 2) return m
    const aIds = new Set(details[0].results.map((r) => r.chunk_id))
    const bIds = new Set(details[1].results.map((r) => r.chunk_id))
    aIds.forEach((id) => m.set(id, bIds.has(id) ? "both" : "A"))
    bIds.forEach((id) => { if (!aIds.has(id)) m.set(id, "B") })
    return m
  }, [details])

  return (
    <Modal
      visible={open}
      onCancel={onClose}
      title="对比检索"
      footer={null}
      width={1100}
    >
      {loading || !details ? (
        <div className="flex justify-center py-12"><Spin /></div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {details.map((d, i) => (
            <div key={d.id} className="flex flex-col gap-2">
              <div className="rounded-md border bg-muted/30 p-2 text-xs">
                <div className="mb-1 font-medium">
                  {i === 0 ? "A" : "B"}: <span className="font-mono">{d.query}</span>
                </div>
                <div className="flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
                  {d.params && (() => {
                    const p = d.params as Record<string, unknown>
                    return (
                      <>
                        <span>top_k={String(p.top_k)}</span>
                        <span>bm25={String(p.bm25_weight)}</span>
                        <span>vec={String(p.vector_weight)}</span>
                        {Boolean(p.rerank_enabled) && <span>rerank</span>}
                        {p.score_threshold != null && p.score_threshold !== 0 && (
                          <span>≥{String(p.score_threshold)}</span>
                        )}
                      </>
                    )
                  })()}
                  {d.latency_ms != null && <span>· {d.latency_ms}ms</span>}
                </div>
              </div>
              <div className="flex max-h-[60vh] flex-col gap-1.5 overflow-y-auto">
                {d.results.length === 0 ? (
                  <Empty description="无召回" />
                ) : d.results.map((r) => {
                  const which = diffMap.get(r.chunk_id)
                  const tone =
                    which === "both" ? "border-blue-400 bg-blue-50/40 dark:bg-blue-950/20" :
                    which === "A" && i === 0 ? "border-amber-400 bg-amber-50/40 dark:bg-amber-950/20" :
                    which === "B" && i === 1 ? "border-emerald-400 bg-emerald-50/40 dark:bg-emerald-950/20" :
                    "opacity-50"
                  return (
                    <div key={r.chunk_id} className={`rounded-md border p-2 text-xs ${tone}`}>
                      <div className="mb-1 flex items-center gap-2">
                        <Tag size="small" color={r.score >= 0.5 ? "green" : "red"}>
                          {(r.score * 100).toFixed(1)}%
                        </Tag>
                        <span className="line-clamp-1 text-muted-foreground">{r.title}</span>
                      </div>
                      <p className="line-clamp-2">{r.content}</p>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
          <div className="col-span-2 flex flex-wrap gap-3 border-t pt-2 text-[11px] text-muted-foreground">
            <span><span className="inline-block size-2.5 rounded-sm border border-blue-400 bg-blue-50/40" /> 共有</span>
            <span><span className="inline-block size-2.5 rounded-sm border border-amber-400 bg-amber-50/40" /> 仅 A 命中</span>
            <span><span className="inline-block size-2.5 rounded-sm border border-emerald-400 bg-emerald-50/40" /> 仅 B 命中</span>
            <span className="ml-auto">
              {(() => {
                const vs = Array.from(diffMap.values())
                const both = vs.filter((v) => v === "both").length
                const aOnly = vs.filter((v) => v === "A").length
                const bOnly = vs.filter((v) => v === "B").length
                return `共 ${diffMap.size} 个 chunk · 共有 ${both} · A 独 ${aOnly} · B 独 ${bOnly}`
              })()}
            </span>
          </div>
        </div>
      )}
    </Modal>
  )
}

interface RetrievalLogDetailLite {
  id: string
  query: string
  params: Record<string, unknown> | null
  latency_ms: number | null
  results: RetrievalResult[]
}

// ─── M3 — Add-to-Golden-Dataset modal ────────────────────────────

function AddToDatasetModal({
  open, onClose, kbId, query, chunkIds,
}: {
  open: boolean
  onClose: () => void
  kbId: string
  query: string
  chunkIds: string[]
}) {
  const [datasets, setDatasets] = useState<Array<{ id: string; name: string }>>([])
  const [loading, setLoading] = useState(false)
  const [datasetId, setDatasetId] = useState<string>("")
  const [newDatasetName, setNewDatasetName] = useState("")
  const [expectedAnswer, setExpectedAnswer] = useState("")
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    knowledgeApi.listEvalDatasets(kbId)
      .then((list) => {
        setDatasets(list.map((d) => ({ id: d.id, name: d.name })))
        if (list.length > 0 && !datasetId) setDatasetId(list[0].id)
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, kbId])

  async function handleSubmit() {
    if (!query.trim()) {
      Toast.error("查询为空")
      return
    }
    setSubmitting(true)
    try {
      let targetId = datasetId
      // If user typed a new dataset name, create it first
      if (newDatasetName.trim() && !targetId) {
        const ds = await knowledgeApi.createEvalDataset(kbId, {
          name: newDatasetName.trim(),
        })
        targetId = ds.id
      }
      if (!targetId) {
        Toast.error("请选择或新建测试集")
        return
      }
      await knowledgeApi.addEvalQuestion(targetId, {
        question: query,
        expected_answer: expectedAnswer.trim() || undefined,
        expected_chunk_ids: chunkIds,
      })
      Toast.success("已加入测试集")
      onClose()
      setNewDatasetName("")
      setExpectedAnswer("")
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "加入失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      visible={open}
      onCancel={onClose}
      onOk={handleSubmit}
      title="加入 Golden Dataset"
      okText="保存"
      cancelText="取消"
      confirmLoading={submitting}
      width={520}
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium">查询</label>
          <Input value={query} disabled />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium">预期命中片段</label>
          <span className="text-xs text-muted-foreground">
            当前结果中的 {chunkIds.length} 个 chunk 将被记录为该 query 的预期命中
          </span>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium">已有测试集</label>
          {loading ? (
            <Spin size="small" />
          ) : (
            <Select
              value={datasetId || undefined}
              onChange={(v) => setDatasetId((v as string) ?? "")}
              placeholder={datasets.length === 0 ? "暂无，下方新建" : "选择测试集"}
              showClear
              disabled={datasets.length === 0}
            >
              {datasets.map((d) => (
                <Select.Option key={d.id} value={d.id}>{d.name}</Select.Option>
              ))}
            </Select>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium">或新建测试集</label>
          <Input
            value={newDatasetName}
            onChange={(v) => { setNewDatasetName(v); if (v) setDatasetId("") }}
            placeholder="测试集名称"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium">参考答案（可选）</label>
          <Input
            value={expectedAnswer}
            onChange={setExpectedAnswer}
            placeholder="留空表示仅记录预期命中片段"
          />
        </div>
      </div>
    </Modal>
  )
}

// ─── Sub-components ──────────────────────────────────────────────

function KBHealthBar({
  health, counts,
}: {
  health: GovernanceHealth
  counts: { chunk_count: number; document_count: number } | null
}) {
  const score = Math.round(health.health_score)
  const color = score >= 70 ? "green" : score >= 50 ? "amber" : "red"
  const label = score >= 70 ? "健康" : score >= 50 ? "需关注" : "状态较差"
  const facets = health.facets || {}
  // Each facet score is 0-100, NOT a count. Use full names with " 质量"/
  // "度" suffix so users don't confuse them with chunk / document counts.
  const facetLabels: Record<string, string> = {
    chunk_quality: "Chunk 质量",
    coverage: "覆盖度",
    freshness: "新鲜度",
    availability: "可用性",
    answer_quality: "答案质量",
  }
  return (
    <div
      className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/30 px-3 py-2 text-xs"
      title="评分均为 0-100 的健康度指标；右侧『分块 / 文档』为实际数量"
    >
      <span className="flex items-center gap-1.5 font-medium">
        KB 健康度
        <Tag color={color}>{score} / 100</Tag>
        <span className="text-muted-foreground">{label}</span>
      </span>
      <span className="text-muted-foreground">·</span>
      {Object.entries(facets).map(([k, f]) => (
        <span key={k} className="flex items-center gap-1 text-muted-foreground">
          {facetLabels[k] ?? k}
          <span className="font-mono text-foreground">{Math.round(f.score)}分</span>
        </span>
      ))}
      <span className="ml-auto flex items-center gap-3 text-muted-foreground">
        {counts && (
          <span>
            <span className="font-mono text-foreground">{counts.chunk_count}</span> 分块
            <span className="mx-1.5">·</span>
            <span className="font-mono text-foreground">{counts.document_count}</span> 文档
          </span>
        )}
        {health.alerts && health.alerts.length > 0 && (
          <span>
            <span className="mx-1.5">·</span>
            {health.alerts.length} 条治理告警
          </span>
        )}
      </span>
    </div>
  )
}

function ParamsSummary({ p }: { p: SearchParams }) {
  return (
    <span className="text-xs text-muted-foreground">
      top_k={p.top_k} · bm25={p.bm25_weight} · vec={p.vector_weight}
      {p.score_threshold > 0 && ` · ≥${p.score_threshold}`}
      {p.rerank_enabled && " · rerank"}
    </span>
  )
}

function ParamsPanel({
  value, onChange, embeddingOptions, rerankerOptions, tagOptions, llmOptions, llmId, onLlmChange,
  recommendations, onApplyRecommendation,
  thresholdSuggestion,
  onSaveAsDefault, savingDefault,
}: {
  value: SearchParams
  onChange: (next: SearchParams) => void
  embeddingOptions: RegistryEntry[]
  rerankerOptions: RegistryEntry[]
  tagOptions: string[]
  llmOptions: RegistryEntry[]
  llmId: string
  onLlmChange: (id: string) => void
  recommendations: RecommendationRow[]
  onApplyRecommendation: (r: RecommendationRow) => void
  thresholdSuggestion: {
    sample_size: number
    floor: number | null
    recommended: number | null
  } | null
  onSaveAsDefault: () => void
  savingDefault: boolean
}) {
  const update = <K extends keyof SearchParams>(key: K, v: SearchParams[K]) =>
    onChange({ ...value, [key]: v })

  return (
    <div className="flex flex-col gap-4">
      {recommendations.length > 0 && (
        <div className="flex flex-col gap-2 rounded-md border bg-muted/30 p-2.5">
          <div className="flex items-center gap-1.5 text-xs font-medium">
            <span>📊 推荐参数</span>
            <InfoTip text="系统根据这个知识库的历史使用情况，自动给不同类型的查询（比如「故障排查」「概念解释」）推荐一组合适的参数组合。点击 chip 一键应用" />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {recommendations.map((r) => {
              const usable = r.sample_size >= 10 ? r.payload.tuned : r.payload.base
              const lowSample = r.sample_size < 10
              return (
                <button
                  key={r.query_type}
                  type="button"
                  onClick={() => onApplyRecommendation(r)}
                  className="flex items-center gap-1.5 rounded-md border bg-background px-2 py-1 text-xs hover:bg-muted"
                  title={`${r.payload.note}（样本 ${r.sample_size}）`}
                >
                  <span className="font-medium">{r.query_type}</span>
                  <span className="text-muted-foreground">
                    bm25={usable.bm25_weight}/vec={usable.vector_weight}/k={usable.top_k}
                    {usable.rerank && " ·rerank"}
                  </span>
                  {lowSample && <Tag size="small" color="grey">基线</Tag>}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* 4 个功能模块，每个一张浅底卡片：召回控制 / 精排 / 相关度过滤 / 模型覆盖 */}

      <ModuleBox icon={Crosshair} title="召回控制" subtitle="· 决定从知识库捞回哪些候选">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <Field
            label="返回数量"
            className="w-24"
            tip="「top_k」是检索领域的工程惯用语，意思是「按相关度排序后取前 K 条」。这里就是控制一次检索最多返回多少条结果。值小召回精，值大覆盖广。生成答案时通常 5 条够用，调试时可以多看几条"
          >
            <InputNumber
              value={value.top_k}
              onChange={(v) => update("top_k", typeof v === "number" ? v : Number(v) || 1)}
              min={1} max={100}
              style={{ width: "100%" }}
            />
          </Field>

          <Field
            label={`关键字匹配  ·  ${value.bm25_weight.toFixed(2)}`}
            className="min-w-[200px] flex-1"
            tip="BM25 是 1980 年代发明的经典文本检索算法，按你的查询词在原文里出现的次数和词的稀缺度打分（罕见词权重高、常用词权重低）。这里的权重决定 BM25 分数在最终排序里的影响力。1=正常，0=完全不看字面，2=双倍重视。查代码 ID、专有名词、错误码这种「字面命中比意思重要」的场景调高有用"
          >
            <Slider
              value={value.bm25_weight}
              onChange={(v) => update("bm25_weight", typeof v === "number" ? v : 1)}
              min={0} max={2} step={0.1}
            />
          </Field>

          <Field
            label={`语义匹配  ·  ${value.vector_weight.toFixed(2)}`}
            className="min-w-[200px] flex-1"
            tip="「向量检索」把每段文字用 AI 模型转成几百~上千维的数字向量，再算两个向量在空间里的「角度」是否接近——AI 就能理解「数据库」和「DB」、「登录失败」和「无法 sign in」其实是同一回事。这里的权重决定语义匹配在最终排序里的影响力。1=正常，查抽象问题（「怎么实现 X」「为什么会 Y」）时主要靠这个"
          >
            <Slider
              value={value.vector_weight}
              onChange={(v) => update("vector_weight", typeof v === "number" ? v : 1)}
              min={0} max={2} step={0.1}
            />
          </Field>
        </div>
      </ModuleBox>

      {/* 中段两模块并列：精排 + 相关度过滤（都偏轻量，单 slider/single switch+select） */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">

      <ModuleBox icon={Sparkles} title="精排" subtitle="· 用更准的模型给候选重新打分">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <Field
            label="启用 rerank"
            tip="Reranker（重排器）是一类专门做「检索后精排」的 AI 模型，会把查询和每条候选结果一起喂进去做精细打分（cross-encoder 架构）——比初步检索的 dense/BM25 各自打分更准，但每次推理更慢。能把真相关的内容顶上来，代价是 +几百毫秒延迟。建议正式问答开，纯调试看初步检索时关"
          >
            <div className="flex h-8 items-center">
              <Switch
                checked={value.rerank_enabled}
                onChange={(v) => update("rerank_enabled", v)}
              />
            </div>
          </Field>

          <Field label="reranker 模型" className="min-w-[200px] flex-1">
            <Select
              value={value.rerank_registry_id || undefined}
              onChange={(v) => update("rerank_registry_id", (v as string) ?? "")}
              placeholder={value.rerank_enabled ? "KB 默认 reranker" : "未启用"}
              showClear
              disabled={!value.rerank_enabled}
            >
              {rerankerOptions.map((m) => (
                <Select.Option key={m.id} value={m.id}>
                  {m.display_name || m.model_id}
                </Select.Option>
              ))}
            </Select>
          </Field>
        </div>
      </ModuleBox>

      <ModuleBox icon={Filter} title="相关度过滤" subtitle="· 卡掉看似相似实际无关的结果">
        <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
          <Field
            label={`最低门槛  ·  ${value.score_threshold > 0 ? value.score_threshold.toFixed(3) : "关闭"}`}
            tip="这里的「相关度」= 余弦相似度（向量空间里两个方向的接近程度，0~1）。这个门槛过滤掉相似度低于此值的结果。值越高越严，0=不过滤。建议参考下方 chip 给出的「模型 floor」+0.02——设到 floor 之上才能让无关查询彻底 0 召回"
            className="w-72"
          >
            <Slider
              value={value.score_threshold}
              onChange={(v) => update("score_threshold", typeof v === "number" ? v : 0)}
              min={0} max={1} step={0.005}
            />
          </Field>
          {thresholdSuggestion?.recommended != null && (
            <button
              type="button"
              onClick={() =>
                update("score_threshold", thresholdSuggestion.recommended ?? 0)
              }
              className="rounded-md border bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted"
              title={
                "「模型 floor」= 这个 AI 模型对本知识库无关内容的「噪声基线」。" +
                "比如 floor=0.71 意味着任何完全无关的查询，跟知识库的相似度也会到 0.71。" +
                "把门槛设到 floor + 0.02 以上，无关查询就能 0 召回。点击一键应用建议值"
              }
            >
              💡 建议 ≥ {thresholdSuggestion.recommended.toFixed(2)}
              <span className="ml-1 opacity-60">
                （floor {thresholdSuggestion.floor?.toFixed(2)}）
              </span>
            </button>
          )}
        </div>
      </ModuleBox>

      </div>

      <ModuleBox
        icon={Filter}
        title="标签过滤"
        subtitle="· 限定召回必须 / 至少 / 不含某些标签（来自 KB 字典）"
      >
        <div className="grid grid-cols-1 gap-x-4 gap-y-3 md:grid-cols-3">
          <Field
            label="任一命中（any of）"
            tip="召回 chunk 的 tags 至少包含这里勾选的一个标签。多选语义 OR；留空= 不约束。常用于扩大检索领域"
          >
            <Select
              multiple
              value={value.tag_any_of}
              onChange={(v) => update("tag_any_of", (v as string[]) ?? [])}
              placeholder="不约束"
              showClear
              filter
            >
              {tagOptions.map((t) => (
                <Select.Option key={`any-${t}`} value={t}>{t}</Select.Option>
              ))}
            </Select>
          </Field>

          <Field
            label="全部命中（all of）"
            tip="召回 chunk 的 tags 必须同时包含所有勾选项。多选语义 AND；留空= 不约束。用于「同时具备 X 和 Y 标签」的精准筛选"
          >
            <Select
              multiple
              value={value.tag_all_of}
              onChange={(v) => update("tag_all_of", (v as string[]) ?? [])}
              placeholder="不约束"
              showClear
              filter
            >
              {tagOptions.map((t) => (
                <Select.Option key={`all-${t}`} value={t}>{t}</Select.Option>
              ))}
            </Select>
          </Field>

          <Field
            label="排除（not）"
            tip="召回 chunk 的 tags 不允许包含勾选项中的任意一个。用于排除不想看到的话题域，比如把营销内容排除掉只看售后"
          >
            <Select
              multiple
              value={value.tag_not}
              onChange={(v) => update("tag_not", (v as string[]) ?? [])}
              placeholder="不约束"
              showClear
              filter
            >
              {tagOptions.map((t) => (
                <Select.Option key={`not-${t}`} value={t}>{t}</Select.Option>
              ))}
            </Select>
          </Field>
        </div>
      </ModuleBox>

      <ModuleBox icon={Cpu} title="模型临时覆盖" subtitle="· 仅本次查询生效，不改 KB 配置">
        <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
          <Field
            label="向量模型"
            tip="Embedding（向量化）模型把文字编码成几百~几千维的数字向量。同一意思的内容向量空间位置接近，AI 才能跨语言、跨表达方式找相关内容。换模型可以测对比效果，但仅本次查询生效，不影响知识库已建立的索引（要持久化换模型需在「知识库配置」改并重处理）"
            className="min-w-[200px] flex-1"
          >
            <Select
              value={value.embedding_registry_id || undefined}
              onChange={(v) => update("embedding_registry_id", (v as string) ?? "")}
              placeholder="使用 KB 默认"
              showClear
            >
              {embeddingOptions.map((m) => (
                <Select.Option key={m.id} value={m.id}>
                  {m.display_name || m.model_id}
                </Select.Option>
              ))}
            </Select>
          </Field>

          <Field
            label="答案 LLM"
            tip="LLM = Large Language Model（大语言模型），就是 GPT、Claude、Qwen 这类能读取文字并生成回答的 AI。这里选「生成答案」时调用哪个 LLM 把检索到的内容总结成回答。不同 LLM 写答案的风格、准度、速度、成本不一样。注意：这里只影响「生成答案」步骤，不影响检索本身"
            className="min-w-[200px] flex-1"
          >
            <Select
              value={llmId || undefined}
              onChange={(v) => onLlmChange((v as string) ?? "")}
              placeholder="选择 LLM"
            >
              {llmOptions.map((m) => (
                <Select.Option key={m.id} value={m.id}>
                  {m.display_name || m.model_id}
                </Select.Option>
              ))}
            </Select>
          </Field>
        </div>
      </ModuleBox>

      <div className="flex justify-end">
        <Button
          theme="light"
          size="small"
          onClick={onSaveAsDefault}
          loading={savingDefault}
        >
          存为知识库默认
        </Button>
      </div>
    </div>
  )
}

/** 表单 cell：label 行（带可选 tip） + 内容 + 可选额外节点（如 chip）。
 * 把 ParamsPanel 里反复出现的 `<div flex flex-col gap-1><label>...</label>...</div>`
 * 抽出来，让上层 grid 节奏一致 */
function Field({
  label,
  tip,
  className,
  children,
}: {
  label: string
  tip?: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={"flex flex-col gap-1.5 " + (className ?? "")}>
      <label className="text-xs text-muted-foreground">
        {label}
        {tip && <InfoTip text={tip} className="ml-1" />}
      </label>
      {children}
    </div>
  )
}

/** 参数面板的功能模块：浅底卡片 + 顶部图标标题 + 副标题 + 内容区。
 * children 自己控制 layout（一般 flex flex-wrap items-end gap-...），
 * ModuleBox 不强加 flex 结构，给每组最大灵活性 */
function ModuleBox({
  icon: Icon,
  title,
  subtitle,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-muted/20 px-3.5 pb-3 pt-2.5">
      <div className="mb-2.5 flex items-baseline gap-1.5">
        <Icon className="size-3.5 shrink-0 -translate-y-px text-primary/70" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-foreground/75">
          {title}
        </span>
        {subtitle && (
          <span className="text-[10px] text-muted-foreground/80">{subtitle}</span>
        )}
      </div>
      {children}
    </div>
  )
}

function HistoryItem({
  log, active, checked, onClick, onToggleCompare,
}: {
  log: RetrievalLogItem
  active: boolean
  checked: boolean
  onClick: () => void
  onToggleCompare: () => void
}) {
  const empty = log.result_count === 0
  return (
    <div
      className={`flex items-start gap-2 rounded-md border p-2 transition-colors hover:bg-muted ${
        active ? "border-primary bg-muted" : ""
      }`}
    >
      <input
        type="checkbox"
        className="mt-0.5"
        checked={checked}
        onChange={onToggleCompare}
        onClick={(e) => e.stopPropagation()}
        title="勾选两条进行对比"
      />
      <button
        type="button"
        onClick={onClick}
        className="flex-1 min-w-0 text-left"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="line-clamp-1 text-sm">{log.query}</span>
          <span className="flex shrink-0 items-center gap-1">
            {log.is_test && (
              <span title="测试性检索，不计入治理统计">
                <Tag size="small" color="grey">测试</Tag>
              </span>
            )}
            {empty && <Tag size="small" color="red">无召回</Tag>}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <Tag size="small" color="grey">{log.query_type}</Tag>
          <span>top_k={log.top_k}</span>
          <span>·</span>
          <span>{log.result_count} 条</span>
          {log.latency_ms != null && (<>
            <span>·</span>
            <span>{log.latency_ms}ms</span>
          </>)}
        </div>
        <RelativeTime iso={log.created_at} />
      </button>
    </div>
  )
}

function RelativeTime({ iso }: { iso: string }) {
  const text = useMemo(() => {
    const ts = new Date(iso).getTime()
    const diff = Date.now() - ts
    if (diff < 60_000) return "刚刚"
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
    return new Date(iso).toLocaleString("zh-CN")
  }, [iso])
  return <span className="text-[10px] text-muted-foreground">{text}</span>
}

function AnswerCard({
  answer, streaming, meta, error,
}: {
  answer: string
  streaming: boolean
  meta: { model: string | null; tokens: { prompt: number; completion: number; total: number } | null; cost_usd: number | null } | null
  error: string | null
}) {
  return (
    <div className="rounded-md border bg-muted/20 p-4">
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        <span>🤖 生成答案</span>
        {streaming && <Spin size="small" />}
        {meta?.model && (
          <span className="ml-auto flex items-center gap-2">
            <Tag size="small">{meta.model}</Tag>
            {meta.tokens && (
              <span>
                {meta.tokens.prompt} prompt · {meta.tokens.completion} completion · {meta.tokens.total} total
              </span>
            )}
            {meta.cost_usd != null && meta.cost_usd > 0 && (
              <span className="font-mono">${meta.cost_usd.toFixed(6)}</span>
            )}
          </span>
        )}
      </div>
      {error ? (
        <p className="text-sm text-red-500">{error}</p>
      ) : (
        // max-w-[80ch] keeps each line at a comfortable reading width
        // (~80 chars) regardless of how wide the panel itself is. The
        // outer flex card still spans the column; only the prose body is
        // capped.
        <div className="prose prose-sm max-w-[80ch] dark:prose-invert">
          <MarkdownRender raw={answer || "..."} format="md" components={markdownCodeBlockComponents} />
          {streaming && (
            <span className="ml-1 inline-block h-3 w-1 animate-pulse bg-foreground" />
          )}
        </div>
      )}
    </div>
  )
}

function ChunkCard({
  index, result, feedback, onFeedback,
}: {
  index: number
  result: RetrievalResult
  feedback?: "up" | "down"
  onFeedback?: (sentiment: "up" | "down") => void
}) {
  const [expanded, setExpanded] = useState(false)
  // Detect whether the line-clamped paragraph is actually overflowing.
  // Short content (1-2 lines) shouldn't show a "展开全文" toggle that
  // does nothing visible.
  const [overflows, setOverflows] = useState(false)
  const contentRef = useRef<HTMLParagraphElement>(null)

  // Reset expansion when the underlying content changes (e.g. user clicked
  // a history snapshot rendering a different chunk).
  useEffect(() => { setExpanded(false) }, [result.content])

  // Measure only in collapsed mode — that's when line-clamp clips.
  useEffect(() => {
    const el = contentRef.current
    if (!el || expanded) return
    setOverflows(el.scrollHeight > el.clientHeight + 1)
  }, [result.content, expanded])

  // 主分数 = rerank_score ?? dense_score（统一校准的相关度，跨 query 可比）
  // BM25-only 命中：无可校准相关度数 → 显示「词面命中」标签，不显示数字
  const dense = result.dense_score
  const rerank = result.rerank_score
  const primary = rerank ?? dense  // null 仅在 BM25-only 时
  const isBm25Only = primary == null && result.bm25_score != null

  type ToneColor = "green" | "amber" | "red" | "grey"
  const tone: ToneColor =
    primary == null ? "grey" : primary >= 0.75 ? "green" : primary >= 0.6 ? "amber" : "red"
  const toneLabel =
    primary == null
      ? (isBm25Only ? "词面命中" : "—")
      : primary >= 0.75 ? "强相关"
      : primary >= 0.6 ? "中等"
      : "弱相关"

  // 主 tag 文本：「相关度 0.71 · 强相关」/ BM25-only 时只「词面命中」
  const primaryTagText = primary == null ? toneLabel : `相关度 ${primary.toFixed(2)} · ${toneLabel}`
  const primaryTagTitle =
    primary == null
      ? "仅 BM25 词面命中，无统一相关度信号"
      : rerank != null
        ? `Reranker 评估分（rerank ${rerank.toFixed(3)}）`
        : `向量相似度（dense ${dense?.toFixed(3) ?? "—"}）`

  // 详情行的"排序值" hover 提示：解释 RRF 不是相关度
  const fusedTitle =
    "工程上叫 RRF 融合分（Reciprocal Rank Fusion = 倒数排名融合）。语义分和字面分量纲不同没法直接相加，RRF 用 1/(60+排名) 把两个排名合并成一个分。这个分本质是「排队号倒数和」，量级 ~1/61≈0.016，**只用来排序，不代表相关度高低**——大小完全不可读"

  const meta = result.metadata as Record<string, unknown> | null
  const keywords = (meta?.keywords as string[] | undefined) || []
  const questions = (meta?.questions as string[] | undefined) || []
  const isRaptor = result.level >= 1 && Array.isArray(meta?.raptor_children)

  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">#{index}</span>
        <span title={primaryTagTitle}>
          <Tag color={tone}>{primaryTagText}</Tag>
        </span>
        <InfoTip text="这是综合判定的相关度分，0~1，越接近 1 越相关。值取自精排分（如果开了精排）或语义分（rerank ?? dense）——这两个是统一的「相关度」量纲。≥0.75 强相关 / ≥0.6 中等 / 否则弱相关。注意：仅命中字面（BM25-only）时无统一相关度数，标为「词面命中」" />
        <span className="flex items-center gap-1 text-muted-foreground">
          <FileText className="size-3" />
          {result.title || "(未命名)"}
        </span>
        <span className="text-muted-foreground">L{result.level} · pos {result.level}</span>
        {isRaptor && <Tag size="small" color="violet">RAPTOR</Tag>}
      </div>

      {/* 详情行：dense / bm25 / rerank 原始分 + 内部排序（RRF）。
          与主 tag 视觉区隔，仅供调参/调试参考，普通用户可忽略。*/}
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <span className="opacity-60">
          ⊕ 详情
          <InfoTip text="下面这些是给调参/诊断用的原始分数，普通用户看上面的「相关度」就够了。下面的分数有不同口径（量纲不一样），不能直接横向比" className="ml-1" />
        </span>
        {result.dense_score != null && (
          <span>
            语义分
            <InfoTip text="工程上叫 dense_score —— 「向量余弦相似度」。把查询和这段内容用 AI 模型转成几百维向量，再算两个向量的「夹角余弦值」（0~1，越接近 1 角度越小、意思越接近）。所有 chunk 都用同一模型 embed，所以这个分数跨 chunk 可比" className="mx-1" />
            <span className="font-mono">{result.dense_score.toFixed(3)}</span>
          </span>
        )}
        {result.bm25_score != null && (
          <span>
            字面分
            <InfoTip text="工程上叫 bm25_score —— BM25 算法（1980 年代经典文本检索算法）的输出。按你查询词在原文出现的次数 × 词的稀缺度打分（罕见词权重高），数值无固定上限，因文档长度而异，不能跨 chunk 直接比" className="mx-1" />
            <span className="font-mono">{result.bm25_score.toFixed(3)}</span>
          </span>
        )}
        {result.rerank_score != null && (
          <span>
            精排分
            <InfoTip text="工程上叫 rerank_score —— Reranker（重排器）模型的输出，把查询和 chunk 一起读取后联合打分（cross-encoder），比上面分别算的语义分/字面分更准。开了「启用精排」才有这一项" className="mx-1" />
            <span className="font-mono">{result.rerank_score.toFixed(3)}</span>
          </span>
        )}
        <span className="ml-auto">
          排序值
          <InfoTip text={fusedTitle} className="mx-1" />
          <span className="font-mono">{result.score.toFixed(4)}</span>
        </span>
      </div>

      {keywords.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1">
          {keywords.slice(0, 6).map((k, i) => (
            <Tag key={i} size="small">{k}</Tag>
          ))}
        </div>
      )}

      <p
        ref={contentRef}
        className={
          expanded
            ? "max-w-[80ch] whitespace-pre-wrap text-sm"
            : "max-w-[80ch] line-clamp-3 text-sm"
        }
      >
        {result.content}
      </p>

      <div className="mt-2 flex items-center gap-2">
        {overflows && (
          <Button
            theme="borderless"
            size="small"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "收起" : "展开全文"}
          </Button>
        )}
        {questions.length > 0 && (
          <span className="text-[10px] text-muted-foreground">
            生成问题: {questions.slice(0, 2).join(" / ")}
          </span>
        )}
        {onFeedback && (
          <div className="ml-auto flex items-center gap-1">
            <Button
              theme={feedback === "up" ? "solid" : "borderless"}
              type={feedback === "up" ? "primary" : "tertiary"}
              size="small"
              icon={<ThumbsUp className="size-3.5" />}
              onClick={() => onFeedback("up")}
            />
            <Button
              theme={feedback === "down" ? "solid" : "borderless"}
              type={feedback === "down" ? "danger" : "tertiary"}
              size="small"
              icon={<ThumbsDown className="size-3.5" />}
              onClick={() => onFeedback("down")}
            />
          </div>
        )}
      </div>
    </div>
  )
}

