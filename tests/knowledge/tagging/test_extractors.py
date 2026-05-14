"""Spec 25 Plan B — Extractor 纯逻辑单测：mock ModelService 隔离 LLM/embed 调用。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge.tagging.extractors.base import ExtractorDeps, TagCandidate
from app.knowledge.tagging.extractors.hybrid import HybridExtractor
from app.knowledge.tagging.extractors.keybert import (
    KeyBERTExtractor,
    _cosine,
    _extract_phrases,
)
from app.knowledge.tagging.extractors.llm import (
    LLMExtractor,
    _build_dict_hint,
    _extract_json_array,
)
from app.knowledge.tagging.extractors.registry import (
    get_extractor,
    list_providers,
)


# ── registry ─────────────────────────────────────────────────────


def test_registry_lists_three_providers():
    providers = list_providers()
    assert set(providers) == {"keybert", "llm", "hybrid"}


def test_registry_returns_correct_instance():
    assert get_extractor("keybert").name == "keybert"
    assert get_extractor("llm").name == "llm"
    assert get_extractor("hybrid").name == "hybrid"


def test_registry_unknown_raises():
    with pytest.raises(ValueError, match="Unknown"):
        get_extractor("not_a_real_provider")


# ── KeyBERT pure helpers ─────────────────────────────────────────


def test_extract_phrases_dedup_and_filter():
    phrases = _extract_phrases("退款流程 / 退款流程 · 售后 (售后) ★ 1234")
    assert "退款流程" in phrases
    assert "售后" in phrases
    # 纯数字被过滤
    assert "1234" not in phrases
    # 去重保序
    assert phrases.count("退款流程") == 1


def test_extract_phrases_length_bounds():
    """单字符与超长短语都被过滤。"""
    long = "a" * 50
    phrases = _extract_phrases(f"a / 退款 / {long}")
    assert "退款" in phrases
    assert long not in phrases
    assert "a" not in phrases  # < _MIN_PHRASE_LEN


def test_cosine_basic():
    assert _cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert _cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert _cosine([0, 0], [1, 1]) == 0.0  # 零向量 fallback


# ── KeyBERT.extract（mock embedding API）──────────────────────────


@pytest.mark.asyncio
async def test_keybert_returns_top_n_sorted_by_similarity():
    """anchor vec=[1,0]，phrase1=[1,0] sim=1，phrase2=[0,1] sim=0
    → phrase1 出现，phrase2 confidence<=0 被过滤。"""
    fake_svc = MagicMock()
    fake_svc.embed_by_registry = AsyncMock(return_value=[
        [1.0, 0.0],   # anchor (title + content)
        [1.0, 0.0],   # 退款
        [0.0, 1.0],   # 售后
    ])
    deps = ExtractorDeps(
        model_svc=fake_svc,
        kb_embedding_registry_id="dummy",
        kb_llm_registry_id=None,
        dictionary_canonicals=[],
    )
    ext = KeyBERTExtractor()
    out = await ext.extract(
        title="退款", content="售后", max_n=5, deps=deps,
    )
    # sim>0 的项保留；售后 sim=0 被 confidence>0 filter 掉
    assert len(out) == 1
    assert out[0].tag == "退款"
    assert out[0].source == "keybert"


@pytest.mark.asyncio
async def test_keybert_returns_empty_when_no_registry():
    """KB 没配 embedding registry → 直接返回 []。"""
    deps = ExtractorDeps(
        model_svc=MagicMock(),
        kb_embedding_registry_id=None,
        kb_llm_registry_id=None,
        dictionary_canonicals=[],
    )
    out = await KeyBERTExtractor().extract(
        title="x", content="y", max_n=5, deps=deps,
    )
    assert out == []


@pytest.mark.asyncio
async def test_keybert_swallows_embed_exceptions():
    """embedding 调用抛异常 → 返回 []，不向上传播。"""
    fake_svc = MagicMock()
    fake_svc.embed_by_registry = AsyncMock(side_effect=RuntimeError("embed boom"))
    deps = ExtractorDeps(
        model_svc=fake_svc,
        kb_embedding_registry_id="dummy",
        kb_llm_registry_id=None,
        dictionary_canonicals=[],
    )
    out = await KeyBERTExtractor().extract(
        title="退款", content="售后", max_n=5, deps=deps,
    )
    assert out == []


# ── LLM helpers ──────────────────────────────────────────────────


def test_build_dict_hint_empty():
    assert "字典为空" in _build_dict_hint([])


def test_build_dict_hint_truncates_at_50():
    canon = [f"t{i}" for i in range(75)]
    hint = _build_dict_hint(canon)
    assert "t0" in hint
    assert "t49" in hint
    assert "t50" not in hint
    assert "75" in hint


def test_extract_json_array_handles_messy_output():
    """LLM 经常返回 ```json ...``` 包裹 / 前后有解释 / 行内 markdown。"""
    raw = '说明：\n```json\n[{"tag": "退款", "confidence": 0.9}]\n```\n'
    parsed = _extract_json_array(raw)
    assert parsed == [{"tag": "退款", "confidence": 0.9}]


def test_extract_json_array_returns_empty_on_garbage():
    assert _extract_json_array("not json") == []
    assert _extract_json_array("") == []


# ── LLMExtractor（mock chat）─────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_extractor_parses_response():
    fake_svc = MagicMock()
    fake_svc.chat_by_registry = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps([
            {"tag": "退款", "confidence": 0.92},
            {"tag": "售后", "confidence": 0.81},
        ])}}],
    })
    deps = ExtractorDeps(
        model_svc=fake_svc,
        kb_embedding_registry_id=None,
        kb_llm_registry_id="dummy_llm",
        dictionary_canonicals=["退款"],
    )
    out = await LLMExtractor().extract(
        title="售后", content="x", max_n=5, deps=deps,
    )
    assert [c.tag for c in out] == ["退款", "售后"]
    assert all(c.source == "llm" for c in out)
    assert out[0].confidence == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_llm_extractor_no_registry_returns_empty():
    deps = ExtractorDeps(
        model_svc=MagicMock(),
        kb_embedding_registry_id=None,
        kb_llm_registry_id=None,
        dictionary_canonicals=[],
    )
    out = await LLMExtractor().extract(
        title="x", content="y", max_n=5, deps=deps,
    )
    assert out == []


@pytest.mark.asyncio
async def test_llm_extractor_swallows_call_failure():
    fake_svc = MagicMock()
    fake_svc.chat_by_registry = AsyncMock(side_effect=ConnectionError("upstream"))
    deps = ExtractorDeps(
        model_svc=fake_svc,
        kb_embedding_registry_id=None,
        kb_llm_registry_id="dummy",
        dictionary_canonicals=[],
    )
    out = await LLMExtractor().extract(
        title="x", content="y", max_n=5, deps=deps,
    )
    assert out == []


@pytest.mark.asyncio
async def test_llm_extractor_dedups_tags():
    """LLM 输出重复 tag 时去重。"""
    fake_svc = MagicMock()
    fake_svc.chat_by_registry = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps([
            {"tag": "退款", "confidence": 0.9},
            {"tag": "退款", "confidence": 0.8},  # 重复
            {"tag": "售后", "confidence": 0.7},
        ])}}],
    })
    deps = ExtractorDeps(
        model_svc=fake_svc,
        kb_embedding_registry_id=None,
        kb_llm_registry_id="x",
        dictionary_canonicals=[],
    )
    out = await LLMExtractor().extract(
        title="x", content="y", max_n=5, deps=deps,
    )
    assert [c.tag for c in out] == ["退款", "售后"]


# ── Hybrid extractor flow ────────────────────────────────────────


@pytest.mark.asyncio
async def test_hybrid_falls_back_to_keybert_when_no_llm():
    """LLM 未配 → 直接返 KeyBERT 截断结果。"""
    fake_svc = MagicMock()
    fake_svc.embed_by_registry = AsyncMock(return_value=[
        [1.0, 0.0],
        [1.0, 0.0],   # 退款 sim=1
        [0.95, 0.31], # 售后 sim≈0.95
        [0.5, 0.87],  # 客服 sim≈0.5
    ])
    deps = ExtractorDeps(
        model_svc=fake_svc,
        kb_embedding_registry_id="dummy",
        kb_llm_registry_id=None,  # 无 LLM
        dictionary_canonicals=[],
    )
    out = await HybridExtractor().extract(
        title="退款", content="售后 客服", max_n=2, deps=deps,
    )
    # KeyBERT 出 max_n*2 候选 → fallback 截 max_n=2
    assert len(out) == 2
    assert all(c.source == "keybert" for c in out)


@pytest.mark.asyncio
async def test_hybrid_uses_llm_when_available():
    """KeyBERT 出候选 → LLM 改写为最终标签。"""
    fake_svc = MagicMock()
    fake_svc.embed_by_registry = AsyncMock(return_value=[
        [1.0, 0.0],
        [1.0, 0.0],   # 退款
        [0.9, 0.4],   # 售后
    ])
    fake_svc.chat_by_registry = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps([
            {"tag": "退款", "confidence": 0.88},
            {"tag": "售后服务", "confidence": 0.75},
        ])}}],
    })
    deps = ExtractorDeps(
        model_svc=fake_svc,
        kb_embedding_registry_id="dummy",
        kb_llm_registry_id="dummy_llm",
        dictionary_canonicals=[],
    )
    out = await HybridExtractor().extract(
        title="退款", content="售后 客服", max_n=2, deps=deps,
    )
    assert [c.tag for c in out] == ["退款", "售后服务"]
    assert all(c.source == "hybrid" for c in out)


def test_tag_candidate_dataclass():
    c = TagCandidate(tag="x", confidence=0.5, source="llm")
    assert c.tag == "x"
    assert c.confidence == 0.5
    assert c.source == "llm"
