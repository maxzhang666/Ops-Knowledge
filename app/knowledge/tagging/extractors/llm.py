"""LLM-based 标签抽取 —— 调小模型从 title+content 抽取主题标签。

prompt 包含字典已有 canonical 列表作为参考，引导命名一致性（同义词收敛）。
confidence 由 LLM 给出（0.0~1.0 浮点）；解析失败时统一给 0.7 兜底。

依赖 ModelService.chat_by_registry — 复用现有 LiteLLM provider 抽象。
"""
from __future__ import annotations

import json
import re

import structlog

from app.knowledge.tagging.extractors.base import (
    AutoTagger,
    ExtractorDeps,
    TagCandidate,
)

logger = structlog.get_logger(__name__)


_PROMPT_TEMPLATE = """你是一个标签提取助手。从给定的标题和正文中提取最能代表主题的标签（关键概念词）。

要求：
1. 仅输出 JSON 数组，格式：[{{"tag": "...", "confidence": 0.0~1.0}}, ...]
2. 最多输出 {max_n} 个标签
3. 每个标签 2~16 字，简洁名词短语，避免长句
4. confidence 反映标签与正文主题的相关度
5. 如果已有字典 canonical 列表，**优先复用列表中的标签**避免同义词分裂；只有当现有标签确实无法覆盖某个主题时才创造新标签

{dict_hint}

标题: {title}
正文:
{content}

仅输出 JSON 数组，不要任何额外文本：
"""

_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def _build_dict_hint(canonicals: list[str]) -> str:
    if not canonicals:
        return "(当前字典为空，可自由命名标签)"
    sample = canonicals[:50]  # 限制 prompt 长度
    formatted = " / ".join(sample)
    suffix = f"（共 {len(canonicals)} 个，已展示前 50）" if len(canonicals) > 50 else ""
    return f"已有字典 canonical 列表，优先复用：\n{formatted}{suffix}"


def _extract_json_array(text: str) -> list:
    """尽力解析 LLM 输出的 JSON 数组；解析失败返回 []。"""
    if not text:
        return []
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return []
    try:
        parsed = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return parsed


class LLMExtractor:
    name = "llm"

    async def extract(
        self,
        *,
        title: str,
        content: str,
        max_n: int,
        deps: ExtractorDeps,
    ) -> list[TagCandidate]:
        if deps.kb_llm_registry_id is None:
            # 预检在 endpoint 层已挡掉用户触发路径；这里仍 log 一行，便于排查
            # 「embed 后 chain 触发 extract」走到这里的场景（同样应在 endpoint 拦）。
            logger.warning("llm_extractor_skip_no_model_id")
            return []

        prompt = _PROMPT_TEMPLATE.format(
            max_n=max_n,
            dict_hint=_build_dict_hint(deps.dictionary_canonicals),
            title=(title or "")[:200],
            content=(content or "")[:6000],
        )
        try:
            response = await deps.model_svc.chat_by_registry(
                deps.kb_llm_registry_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=512,
            )
        except Exception as exc:
            logger.warning(
                "llm_extractor_chat_failed",
                registry_id=str(deps.kb_llm_registry_id),
                error=str(exc)[:200],
                exc_info=True,
            )
            return []

        # 兼容 LiteLLM 返回结构：response['choices'][0]['message']['content']
        raw_text = ""
        try:
            choices = response.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                raw_text = msg.get("content") or ""
        except (AttributeError, IndexError):
            logger.warning(
                "llm_extractor_response_unparseable",
                response_type=type(response).__name__,
            )
            return []

        if not raw_text:
            logger.warning("llm_extractor_empty_response")
            return []

        parsed = _extract_json_array(raw_text)
        if not parsed:
            logger.warning(
                "llm_extractor_no_json_array_in_response",
                preview=raw_text[:200],
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
                conf = float(item.get("confidence", 0.7))
            except (TypeError, ValueError):
                conf = 0.7
            conf = max(0.0, min(1.0, conf))
            out.append(TagCandidate(tag=tag, confidence=conf, source=self.name))
            if len(out) >= max_n:
                break
        return out


_: AutoTagger = LLMExtractor()
