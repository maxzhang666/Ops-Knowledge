import hashlib
import io
import os
import re
import sys

import structlog

# Stub magika before markitdown tries to import it (magika/onnxruntime unavailable on some platforms)
if "magika" not in sys.modules:
    import types
    _magika = types.ModuleType("magika")
    _magika.Magika = None  # type: ignore
    sys.modules["magika"] = _magika

from markitdown import MarkItDown

logger = structlog.get_logger(__name__)

SUPPORTED_TYPES: dict[str, str] = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".docx": "word",
    ".doc": "word",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".csv": "csv",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
}


def sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename)
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    stem, ext = os.path.splitext(name)
    max_stem = 200 - len(ext)
    if len(stem) > max_stem:
        stem = stem[:max_stem]
    return stem + ext


def detect_source_type(filename: str) -> str:
    _, ext = os.path.splitext(filename.lower())
    source_type = SUPPORTED_TYPES.get(ext)
    if source_type is None:
        raise ValueError(f"Unsupported file type: {ext or 'no extension'}")
    return source_type


def compute_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_document(file_data: bytes, filename: str) -> str:
    _, ext = os.path.splitext(filename.lower())
    md = MarkItDown()
    result = md.convert_stream(io.BytesIO(file_data), file_extension=ext)
    text = result.text_content or ""

    if ext == ".pdf" and len(text.strip()) < 50:
        logger.warning("scanned_pdf_detected", filename=filename, text_length=len(text.strip()))

    return text
