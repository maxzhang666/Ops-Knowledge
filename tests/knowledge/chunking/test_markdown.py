from app.knowledge.chunking.markdown import MarkdownStrategy


def test_split_by_headings():
    text = "# Chapter 1\n\nContent.\n\n## Section 1.1\n\nDetails.\n\n# Chapter 2\n\nMore."
    strategy = MarkdownStrategy()
    results = strategy.chunk(text, {"chunk_size": 500})
    assert len(results) >= 3
