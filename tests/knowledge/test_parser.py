import pytest

from app.knowledge.ingestion.parser import sanitize_filename, detect_source_type, compute_file_hash


def test_sanitize_filename():
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("hello world.pdf") == "hello world.pdf"
    assert len(sanitize_filename("a" * 300 + ".pdf")) <= 204


def test_sanitize_filename_control_chars():
    assert sanitize_filename("file\x00name\x1f.txt") == "filename.txt"


def test_detect_source_type():
    assert detect_source_type("report.pdf") == "pdf"
    assert detect_source_type("readme.md") == "markdown"
    assert detect_source_type("doc.docx") == "word"
    assert detect_source_type("page.html") == "html"
    assert detect_source_type("data.csv") == "csv"
    assert detect_source_type("slides.pptx") == "pptx"
    assert detect_source_type("sheet.xlsx") == "xlsx"
    assert detect_source_type("note.txt") == "txt"


def test_detect_source_type_case_insensitive():
    assert detect_source_type("REPORT.PDF") == "pdf"
    assert detect_source_type("Doc.DOCX") == "word"


def test_detect_source_type_unknown():
    with pytest.raises(ValueError, match="Unsupported"):
        detect_source_type("binary.exe")


def test_compute_file_hash():
    data = b"hello world"
    h = compute_file_hash(data)
    assert len(h) == 64
    assert h == compute_file_hash(data)  # deterministic
    assert h != compute_file_hash(b"different")
