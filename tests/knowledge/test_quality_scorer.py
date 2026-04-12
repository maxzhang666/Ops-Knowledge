from app.knowledge.quality.scorer import score_chunk


def test_normal_chunk():
    assert 0.5 <= score_chunk(
        "Well-written paragraph about software engineering. "
        "It covers design patterns and testing."
    ) <= 1.0


def test_very_short():
    assert score_chunk("Hi") < 0.3


def test_empty():
    assert score_chunk("") == 0.0
