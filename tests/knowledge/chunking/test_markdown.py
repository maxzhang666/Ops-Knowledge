"""MarkdownStrategy chunking tests.

M6.6 起 markdown chunker 合并 heading-only section（body < 30 字符 或
< 5 token）。这些测试同时锁住合并行为和原"按标题切多 chunk"的能力。
"""
from app.knowledge.chunking.markdown import MarkdownStrategy


def _content_of(results) -> list[str]:
    return [r.content for r in results]


def test_long_sections_split_normally():
    """每段都有充足正文 → 仍按 heading 切多个 chunk（原行为）"""
    text = (
        "# Chapter 1\n\n"
        + ("Long content paragraph that easily exceeds thirty characters. " * 3)
        + "\n\n## Section 1.1\n\n"
        + ("More substantial details here for retrieval indexing purposes. " * 3)
        + "\n\n# Chapter 2\n\n"
        + ("Yet another well-developed paragraph sitting under chapter two. " * 3)
    )
    results = MarkdownStrategy().chunk(text, {"chunk_size": 500})
    assert len(results) == 3
    headings = [r.metadata["heading"] for r in results]
    assert headings == ["# Chapter 1", "## Section 1.1", "# Chapter 2"]


def test_heading_only_section_merged_into_next():
    """heading 后正文极短 → 不独立 emit，累加到下一个有正文的 section 作为 prefix"""
    text = (
        "## System Overview\n\n"
        "## Frontend\n\n"
        "React 19 SPA with lazy-loaded routes. TanStack Query for server state. "
        "WebSocket for real-time events. Detailed enough to count as substantive."
    )
    results = MarkdownStrategy().chunk(text, {"chunk_size": 500})
    # 两个空 heading 应该合并到唯一一个有正文的 chunk
    assert len(results) == 1
    content = results[0].content
    assert "## System Overview" in content
    assert "## Frontend" in content
    assert "React 19 SPA" in content
    # metadata.heading 取最具体的（最后一个非空）
    assert results[0].metadata["heading"] == "## Frontend"
    # level 取最早 pending 的（外层结构）
    assert results[0].level == 2


def test_directory_page_all_headings_collapses_to_summary():
    """整页全是 heading 没正文（如目录页） → emit 一个汇总 chunk 保留结构信号"""
    text = "# Index\n\n## Part A\n\n## Part B\n\n### Subpart"
    results = MarkdownStrategy().chunk(text, {"chunk_size": 500})
    # 整页都没正文，最终汇总成 1 个 chunk
    assert len(results) == 1
    content = results[0].content
    assert "# Index" in content
    assert "## Part A" in content
    assert "## Part B" in content
    assert "### Subpart" in content


def test_short_body_threshold_chinese():
    """中文短句（split() token 少）也走字符数判定，避免被误判为有正文"""
    text = (
        "## 概述\n\n"
        "简短的占位文本"  # 7 字符 < 30 → heading-only
        "\n\n## 详情\n\n"
        + ("这里有很多很多详细的内容，远远超过三十字符的最小阈值要求，应该被认作是真正的正文内容。" * 2)
    )
    results = MarkdownStrategy().chunk(text, {"chunk_size": 500})
    # 短"概述"section 合并到下一段
    assert len(results) == 1
    content = results[0].content
    assert "## 概述" in content
    assert "## 详情" in content
    assert "详细的内容" in content


def test_empty_input_returns_empty():
    assert MarkdownStrategy().chunk("", {"chunk_size": 500}) == []
    assert MarkdownStrategy().chunk("   \n\n  ", {"chunk_size": 500}) == []
