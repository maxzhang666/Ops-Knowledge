"""Extractor 注册中心 —— provider 字符串路由到 AutoTagger 实例。

KB 配置 kb_tag_settings.auto_tag_provider 是 'keybert'/'llm'/'hybrid'，
extract_tasks 通过 get_extractor(provider) 拿到实例。
"""
from __future__ import annotations

from app.knowledge.tagging.extractors.base import AutoTagger
from app.knowledge.tagging.extractors.hybrid import HybridExtractor
from app.knowledge.tagging.extractors.keybert import KeyBERTExtractor
from app.knowledge.tagging.extractors.llm import LLMExtractor


_REGISTRY: dict[str, AutoTagger] = {
    "keybert": KeyBERTExtractor(),
    "llm": LLMExtractor(),
    "hybrid": HybridExtractor(),
}


def get_extractor(provider: str) -> AutoTagger:
    inst = _REGISTRY.get(provider)
    if inst is None:
        raise ValueError(f"Unknown auto_tag_provider: {provider}")
    return inst


def list_providers() -> list[str]:
    return list(_REGISTRY.keys())
