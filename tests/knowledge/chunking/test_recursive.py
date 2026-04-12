from app.knowledge.chunking.recursive import RecursiveCharacterStrategy


def test_basic_split():
    strategy = RecursiveCharacterStrategy()
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    results = strategy.chunk(text, {"chunk_size": 20, "chunk_overlap": 0})
    assert len(results) >= 2
    for r in results:
        assert r.content.strip()


def test_empty_text():
    strategy = RecursiveCharacterStrategy()
    results = strategy.chunk("", {"chunk_size": 500, "chunk_overlap": 50})
    assert len(results) == 0
