"""Spec 25 Plan B §3.1 — AutoTagger 抽象。

extractor 是**纯计算 / 异步函数**，不接 DB / 不查字典。
字典 normalize 与拒绝列表过滤由 extract_tasks 层处理，extractor 只负责
"从 title+content 中产生 raw candidates"。

deps 字典统一注入运行时依赖（ModelService / KB embedding registry / KB LLM
registry / dictionary canonicals 引导），便于测试 mock。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class TagCandidate:
    """Extractor 输出的候选项；后续由 normalizer 做字典对齐 + 阈值过滤。"""
    tag: str
    confidence: float
    source: str  # "keybert" / "llm" / "hybrid"


class ExtractorDeps:
    """运行时依赖注入容器（非 dataclass，方便 task 层动态构建）。

    字段：
    - model_svc: ModelService 实例（async API）
    - kb_embedding_registry_id: 用于 KeyBERT 复用 KB 当前 embedding 模型
    - kb_llm_registry_id: 用于 LLM provider 调用
    - dictionary_canonicals: 当前 KB 已有 canonical 列表（LLM prompt 引导
      命名一致性）
    """

    def __init__(
        self,
        model_svc: Any,
        kb_embedding_registry_id: uuid.UUID | None,
        kb_llm_registry_id: uuid.UUID | None,
        dictionary_canonicals: list[str],
    ):
        self.model_svc = model_svc
        self.kb_embedding_registry_id = kb_embedding_registry_id
        self.kb_llm_registry_id = kb_llm_registry_id
        self.dictionary_canonicals = dictionary_canonicals


class AutoTagger(Protocol):
    """所有 extractor 必须实现的接口；纯异步 + 无副作用。"""

    name: str

    async def extract(
        self,
        *,
        title: str,
        content: str,
        max_n: int,
        deps: ExtractorDeps,
    ) -> list[TagCandidate]:
        ...
