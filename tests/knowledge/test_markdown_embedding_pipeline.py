"""端到端串联测试：MarkdownStrategy 输出 → _build_embedding_text 处理。

锁住 M6.6 + M6.7 协同行为：
- A 合并产出的 chunk content 已含 heading
- B 拼接前必须检查 startswith(heading)，避免重复 prefix
- KB 级 threshold override 关闭/打开行为
"""
from app.knowledge.chunking.markdown import MarkdownStrategy
from app.knowledge.embedding.service import _build_embedding_text


def _to_chunk_dict(result) -> dict:
    return {
        "content": result.content,
        "metadata": result.metadata or {},
    }


def test_a_then_b_no_double_heading_prefix():
    """A 合并出的短 chunk（content 已以 heading 开头）走 B → 不应该再拼一次。"""
    text = (
        "## System Overview\n\n"
        "## Frontend\n\n"
        "Short note."  # 11 char, 短到走 B prefix
    )
    chunks = MarkdownStrategy().chunk(text, {"chunk_size": 500})
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.metadata["heading"] == "## Frontend"
    # content 已经包含 "## System Overview\n\n## Frontend\n\nShort note."
    assert chunk.content.startswith("## System Overview")

    embed_input = _build_embedding_text(_to_chunk_dict(chunk))
    # 关键断言：heading "## Frontend" 在 embed input 里**只出现一次**
    assert embed_input.count("## Frontend") == 1
    # 不应该看到 "## Frontend\n\n## System Overview" 这种重复结构
    assert embed_input == chunk.content


def test_b_still_applies_when_content_lacks_heading():
    """长正文 chunk 内容里没有 heading 起头 → B 正常拼 prefix。"""
    chunk = {
        "content": "Short note.",  # 不以 ## 开头
        "metadata": {"heading": "## Frontend"},
    }
    out = _build_embedding_text(chunk)
    assert out.startswith("## Frontend")
    assert "Short note." in out
    assert out.count("## Frontend") == 1


def test_threshold_zero_disables_b_entirely():
    """KB 级 override 设 0 → 任何长度的 chunk 都不加 prefix。"""
    chunk = {
        "content": "tiny",
        "metadata": {"heading": "## H"},
    }
    assert _build_embedding_text(chunk, threshold=0) == "tiny"


def test_threshold_low_makes_more_chunks_qualify():
    """阈值低 → 不在范围内的 chunk 不加 prefix；阈值高 → 加。"""
    chunk = {
        "content": "x" * 50,  # 50 char
        "metadata": {"heading": "## H"},
    }
    # 阈值 30 → 50 char 不属于"短"，不拼
    assert _build_embedding_text(chunk, threshold=30) == "x" * 50
    # 阈值 100 → 50 char 属于"短"，拼
    out = _build_embedding_text(chunk, threshold=100)
    assert out.startswith("## H")


def test_long_chunk_with_heading_stays_unchanged():
    """长 chunk（≥ 阈值）即便有 heading 也保持原样，避免 query/chunk 形态不对称。"""
    long_content = "Lorem ipsum dolor sit amet. " * 10  # ~280 char
    chunk = {
        "content": long_content,
        "metadata": {"heading": "## H"},
    }
    assert _build_embedding_text(chunk) == long_content
