"""Hybrid 标签抽取 —— KeyBERT 出候选 + LLM 校验/改写为字典风格。

流水：
1. KeyBERT 取 max_n*2 候选（confidence 排序）
2. 把候选喂给 LLM，要求"从候选中选 top max_n，按字典风格改写为简洁标签名"
3. LLM 输出作为最终标签，confidence 沿用 KeyBERT 的 cosine（找不到则均值 0.65）

成本接近单 LLM 调用，质量优于单 KeyBERT（同义词更收敛、命名更整齐）。
两段任一失败 → 退化到对方单独输出。
"""
from __future__ import annotations

from app.knowledge.tagging.extractors.base import (
    AutoTagger,
    ExtractorDeps,
    TagCandidate,
)
from app.knowledge.tagging.extractors.keybert import KeyBERTExtractor
from app.knowledge.tagging.extractors.llm import (
    LLMExtractor,
    _build_dict_hint,
    _extract_json_array,
)


_HYBRID_PROMPT = """你是一个标签整理助手。下面是从一段知识内容中由关键短语算法抽取出的候选标签（按相关度排序），请你：

1. 从候选中挑选最能代表主题的标签，最多 {max_n} 个
2. 对候选标签做规范化改写（去掉无意义修饰、统一命名风格），但保持原意
3. 优先复用已有字典 canonical（如果与候选语义相近）
4. 输出 JSON 数组：[{{"tag": "...", "confidence": 0.0~1.0}}, ...]
5. confidence 反映标签与正文主题的相关度

候选标签（按相关度从高到低）：
{candidates}

{dict_hint}

标题: {title}
正文摘要:
{content}

仅输出 JSON 数组，不要任何额外文本：
"""


class HybridExtractor:
    name = "hybrid"

    def __init__(self):
        self._kb = KeyBERTExtractor()

    async def extract(
        self,
        *,
        title: str,
        content: str,
        max_n: int,
        deps: ExtractorDeps,
    ) -> list[TagCandidate]:
        # Step 1：KeyBERT 出候选
        kb_candidates = await self._kb.extract(
            title=title, content=content,
            max_n=max(max_n * 2, 8),
            deps=deps,
        )
        if not kb_candidates or deps.kb_llm_registry_id is None:
            # LLM 不可用 / 无候选 → 直接返回 KeyBERT 结果（前 max_n）
            return kb_candidates[:max_n] if kb_candidates else []

        # Step 2：LLM 改写
        candidates_str = "\n".join(
            f"- {c.tag} ({c.confidence:.2f})" for c in kb_candidates
        )
        prompt = _HYBRID_PROMPT.format(
            max_n=max_n,
            candidates=candidates_str,
            dict_hint=_build_dict_hint(deps.dictionary_canonicals),
            title=(title or "")[:200],
            content=(content or "")[:2000],  # hybrid 不需要完整正文
        )
        try:
            response = await deps.model_svc.chat_by_registry(
                deps.kb_llm_registry_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=512,
            )
        except Exception:
            return kb_candidates[:max_n]

        raw_text = ""
        try:
            choices = response.get("choices") or []
            if choices:
                raw_text = (choices[0].get("message") or {}).get("content") or ""
        except (AttributeError, IndexError):
            return kb_candidates[:max_n]

        parsed = _extract_json_array(raw_text)
        if not parsed:
            return kb_candidates[:max_n]

        # 把 KeyBERT confidence 映射给 LLM 输出（按 tag 名匹配，否则用 LLM 自己给的或均值）
        kb_conf_map = {c.tag.lower(): c.confidence for c in kb_candidates}
        fallback_conf = (
            sum(c.confidence for c in kb_candidates) / len(kb_candidates)
            if kb_candidates else 0.65
        )

        out: list[TagCandidate] = []
        seen: set[str] = set()
        for item in parsed:
            if not isinstance(item, dict):
                continue
            tag = item.get("tag")
            if not isinstance(tag, str):
                continue
            tag = tag.strip()
            if not tag or len(tag) > 32 or tag.lower() in seen:
                continue
            seen.add(tag.lower())
            try:
                llm_conf = float(item.get("confidence", fallback_conf))
            except (TypeError, ValueError):
                llm_conf = fallback_conf
            conf = kb_conf_map.get(tag.lower(), llm_conf)
            conf = max(0.0, min(1.0, conf))
            out.append(TagCandidate(tag=tag, confidence=conf, source=self.name))
            if len(out) >= max_n:
                break
        return out or kb_candidates[:max_n]


_: AutoTagger = HybridExtractor()
