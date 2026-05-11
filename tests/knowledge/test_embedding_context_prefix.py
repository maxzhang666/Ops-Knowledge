"""Embedding contextual prefix (M6.6).

锁住 _build_embedding_text 的核心契约：
- 长 chunk 不动（避免 query/chunk 形态不对称）
- 短 chunk 拼 metadata.heading 作为 prefix
- doc.title 不参与（避免命名噪声）
- 缺失 heading 或 metadata 时安全降级
"""
from app.knowledge.embedding.service import (
    _CONTEXT_PREFIX_CHAR_THRESHOLD,
    _build_embedding_text,
)


def test_long_chunk_unchanged():
    long_content = "x" * (_CONTEXT_PREFIX_CHAR_THRESHOLD + 1)
    chunk = {"content": long_content, "metadata": {"heading": "## Title"}}
    assert _build_embedding_text(chunk) == long_content  # heading 不拼


def test_short_chunk_gets_heading_prefix():
    chunk = {
        "content": "## System Overview",  # 短
        "metadata": {"heading": "## System Overview"},
    }
    out = _build_embedding_text(chunk)
    # 简化版 contextual：拼了 heading\n\ncontent
    assert out.startswith("## System Overview")
    assert "\n\n" in out


def test_short_chunk_no_heading_metadata_unchanged():
    chunk = {"content": "short", "metadata": {}}
    assert _build_embedding_text(chunk) == "short"


def test_short_chunk_metadata_missing_unchanged():
    chunk = {"content": "short"}
    assert _build_embedding_text(chunk) == "short"


def test_doc_title_not_used():
    """B1 约束：不拼 doc.title，避免文件名/版本号噪声"""
    chunk = {
        "content": "short",
        "metadata": {"heading": "## H"},
        "title": "v2-final.md",  # 应该被忽略
    }
    out = _build_embedding_text(chunk)
    assert "v2-final.md" not in out
    assert out.startswith("## H")


def test_threshold_exact_boundary_not_prefixed():
    """长度等于阈值（>= 100）时不加 prefix"""
    content = "x" * _CONTEXT_PREFIX_CHAR_THRESHOLD
    chunk = {"content": content, "metadata": {"heading": "## H"}}
    assert _build_embedding_text(chunk) == content
