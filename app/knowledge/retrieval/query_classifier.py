"""Query classifier (Plan 35 M1).

按 spec `14-knowledge-governance.md §Retrieval Strategy Auto-Tuning` —
不同 query type 适配不同检索策略：

  troubleshooting  报错排查类     → BM25 关键词权重高（错误码精确匹配）
  concept          概念解释类     → 向量权重高（语义相似 > 字面）
  how_to           操作步骤类     → BM25 + 向量持平
  definition       术语定义类     → 向量权重略高
  lookup           简单查询/检索   → BM25 倾向（短词命中）
  other            兜底           → 默认 hybrid 5/5

纯规则匹配，启发式优先 + 关键词列表；不依赖 LLM 也能跑。中英双语。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

QueryType = Literal[
    "troubleshooting", "concept", "how_to", "definition", "lookup", "other",
]


@dataclass
class ClassifyResult:
    type: QueryType
    confidence: float       # 0..1
    rationale: str          # 简短诊断


# 关键词 / 句式 → 类型 (优先级从上往下)
_RULES: list[tuple[QueryType, re.Pattern[str], float, str]] = [
    # troubleshooting：错误 / 异常 / 失败 / 不能 / 报错码
    (
        "troubleshooting",
        re.compile(
            r"(?:报错|出错|错误|异常|失败|无法|不能用|挂了|崩溃|超时|断开|connection\s+(?:refused|reset)|"
            r"timeout|error|fail(?:ed|ure)?|exception|traceback|broken|crash)",
            re.IGNORECASE,
        ),
        0.85,
        "matched error/failure keywords",
    ),
    # how_to：怎么 / 如何 / 步骤 / 怎样 / how to / how do i
    (
        "how_to",
        re.compile(
            r"^(?:如何|怎么|怎样|怎么样)|(?:步骤|流程|教程|guide|tutorial)|"
            r"\bhow\s+(?:to|do\s+(?:i|you|we))",
            re.IGNORECASE,
        ),
        0.8,
        "matched how-to phrasing",
    ),
    # definition：什么是 / 什么叫 / 是什么 / what is / define
    (
        "definition",
        re.compile(
            r"(?:什么是|什么叫|是什么|是啥|是\s*\?|的定义|定义是)|"
            r"\bwhat\s+(?:is|are)\b|\bdefin(?:e|ition)\b|\bmeaning\s+of\b",
            re.IGNORECASE,
        ),
        0.85,
        "matched definition phrasing",
    ),
    # concept：解释 / 原理 / 区别 / 为什么 / explain / why / difference
    (
        "concept",
        re.compile(
            r"(?:解释|原理|为什么|为啥|区别|对比|差异|architecture|mechanism)|"
            r"\bexplain\b|\bwhy\b|\b(?:difference|compare|comparison)\b",
            re.IGNORECASE,
        ),
        0.7,
        "matched concept phrasing",
    ),
    # lookup：精确查找类（短词、专有名词、ID/编号）
    (
        "lookup",
        re.compile(
            r"^[\w\-./]+$|^(?:查询|查找|搜索|find|search|lookup)\s+\S+",
            re.IGNORECASE,
        ),
        0.6,
        "short keyword / lookup query",
    ),
]


def classify(query: str) -> ClassifyResult:
    q = (query or "").strip()
    if not q:
        return ClassifyResult(type="other", confidence=0.0, rationale="empty")
    # lookup 规则要求短查询，先做长度短路：太长就跳过 lookup
    for qtype, pattern, conf, rationale in _RULES:
        if qtype == "lookup" and len(q) > 30:
            continue
        if pattern.search(q):
            return ClassifyResult(type=qtype, confidence=conf, rationale=rationale)
    return ClassifyResult(
        type="other",
        confidence=0.3,
        rationale="no rule matched",
    )


# ── 推荐策略表（基础：每种类型对应的 hybrid 权重 + 建议 top_k）───────

@dataclass
class StrategyRecommendation:
    bm25_weight: float
    vector_weight: float
    top_k: int
    rerank: bool
    note: str


_STRATEGY: dict[QueryType, StrategyRecommendation] = {
    "troubleshooting": StrategyRecommendation(0.7, 0.3, 5, True,
        "错误码 / 异常关键词需要 BM25 精确匹配；rerank 提升结果质量"),
    "concept":         StrategyRecommendation(0.3, 0.7, 6, True,
        "概念问句靠语义相似优于字面命中；rerank 帮助排序"),
    "how_to":          StrategyRecommendation(0.5, 0.5, 5, True,
        "操作步骤兼具关键词与语义；hybrid 5/5 + rerank"),
    "definition":      StrategyRecommendation(0.4, 0.6, 4, False,
        "定义型查询通常 4 条已够；BM25 略低、向量略高"),
    "lookup":          StrategyRecommendation(0.7, 0.3, 5, False,
        "短查询关键词为主，rerank 收益低"),
    "other":           StrategyRecommendation(0.5, 0.5, 5, True,
        "兜底 hybrid 5/5 + rerank"),
}


def recommend_strategy(qtype: QueryType) -> StrategyRecommendation:
    return _STRATEGY[qtype]
