"""Standalone tests for citation extraction (no DB required)."""
from app.chat.citations import extract_citations


def test_extract_citations_basic():
    text = "According to [1] and [2], the answer is yes."
    result = extract_citations(text, 3)
    assert result == [1, 2]


def test_extract_citations_out_of_range():
    text = "See [1], [5], and [10]."
    result = extract_citations(text, 3)
    assert result == [1]


def test_extract_citations_no_citations():
    text = "No citations here."
    result = extract_citations(text, 5)
    assert result == []


def test_extract_citations_zero_chunks():
    text = "Reference [1] should be invalid."
    result = extract_citations(text, 0)
    assert result == []


def test_extract_citations_duplicates():
    text = "[1] is mentioned again [1] and also [2]."
    result = extract_citations(text, 5)
    assert result == [1, 2]


def test_extract_citations_mixed_valid_invalid():
    text = "[0] [1] [2] [3] [4]"
    result = extract_citations(text, 3)
    assert result == [1, 2, 3]


def test_extract_citations_nested_brackets():
    text = "See [[1]] for details."
    result = extract_citations(text, 5)
    assert result == [1]
