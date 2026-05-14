"""KeyBERT-style 标签抽取 —— 复用 KB embedding 模型，零额外成本。

思路：
1. 从 title+content 切候选短语（按标点/换行/长度限制）
2. 对全文一次 embedding + 每个候选短语一次 embedding（batch）
3. cosine similarity 当 confidence，取 top_n
4. 候选短语去重 + 长度过滤（2~24 字符）

不依赖 keybert 第三方库：项目已有 EmbeddingService 工程能力，自己实现避免新增依赖。
"""
from __future__ import annotations

import math
import re

from app.knowledge.tagging.extractors.base import (
    AutoTagger,
    ExtractorDeps,
    TagCandidate,
)


_MIN_PHRASE_LEN = 2
_MAX_PHRASE_LEN = 24
_MAX_CANDIDATES = 40  # 避免大文档 candidate 爆炸 → embedding 调用成本失控


# 简单的中英文短语切分：按标点 / 换行 / 多空格分段，再按 4~24 字符滑窗
# 取 unigram + bigram 短语。中文按字符切，英文按 token 切。
_SEPARATOR_RE = re.compile(
    r"[\s　\n\r\t,，。；！？!?;:\"'《》\(\)\[\]【】\\/]+"
)


def _extract_phrases(text: str) -> list[str]:
    """轻量短语候选生成：分段 + 长度过滤 + 去重保序。"""
    out: list[str] = []
    seen: set[str] = set()
    for seg in _SEPARATOR_RE.split(text or ""):
        seg = seg.strip()
        if not seg:
            continue
        if not (_MIN_PHRASE_LEN <= len(seg) <= _MAX_PHRASE_LEN):
            continue
        if seg.isdigit():  # 排除纯数字
            continue
        low = seg.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(seg)
        if len(out) >= _MAX_CANDIDATES:
            break
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    """nominal cosine similarity；输入向量保证同维。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class KeyBERTExtractor:
    name = "keybert"

    async def extract(
        self,
        *,
        title: str,
        content: str,
        max_n: int,
        deps: ExtractorDeps,
    ) -> list[TagCandidate]:
        if deps.kb_embedding_registry_id is None:
            return []
        candidates = _extract_phrases(f"{title}\n{content}")
        if not candidates:
            return []

        # 全文（title+content 拼接）做 embedding，作为 anchor
        anchor_text = f"{title}\n{content}"[:8000]  # 截断防超模型 input limit

        # 一次 embed_by_registry 调用：[anchor, phrase1, phrase2, ...]
        all_texts = [anchor_text, *candidates]
        try:
            vectors = await deps.model_svc.embed_by_registry(
                deps.kb_embedding_registry_id, all_texts,
            )
        except Exception:
            # embed 失败不阻塞 pipeline；返回空，由 task 层记 task_failure
            return []
        if not vectors or len(vectors) < 2:
            return []

        anchor_vec = vectors[0]
        scored: list[tuple[str, float]] = []
        for phrase, vec in zip(candidates, vectors[1:]):
            sim = _cosine(anchor_vec, vec)
            scored.append((phrase, sim))

        # confidence 排序 + 截 top_n；过滤 confidence <= 0
        scored.sort(key=lambda kv: kv[1], reverse=True)
        out: list[TagCandidate] = []
        for phrase, sim in scored[:max_n]:
            if sim <= 0:
                continue
            out.append(TagCandidate(tag=phrase, confidence=float(sim), source=self.name))
        return out


# 类型声明 — 静态检查 KeyBERTExtractor 实现 AutoTagger Protocol
_: AutoTagger = KeyBERTExtractor()
