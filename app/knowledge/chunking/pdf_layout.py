import re

from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult
from app.knowledge.chunking.recursive import RecursiveCharacterStrategy

# Numbered heading: "1.2.3 Some Heading" or "1. Introduction"
_NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*\.?)\s+(\S.*)$")
# Title-case line: standalone short line in Title Case (not all-caps, not a sentence)
_TITLECASE_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Za-z][a-z]*){0,8}$")
# Page break artifacts from PDF extraction
_PAGE_BREAK_RE = re.compile(r"\n{2,}---+\n{2,}|\f|\n{3,}")
# Page number lines
_PAGE_NUM_RE = re.compile(r"^\s*[-—]?\s*\d{1,4}\s*[-—]?\s*$", re.MULTILINE)


class PDFLayoutStrategy(ChunkingStrategy):
    """Chunk text extracted from PDFs by detecting section structure."""

    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        chunk_size = config.get("chunk_size", 500)
        overlap = config.get("chunk_overlap", 50)

        cleaned = self._clean_pdf_artifacts(text)
        sections = self._split_sections(cleaned)

        fallback = RecursiveCharacterStrategy()
        results: list[ChunkResult] = []
        pos = 0

        for heading, level, body in sections:
            content = f"{heading}\n\n{body}".strip() if heading else body.strip()
            if not content:
                continue
            if len(content) <= chunk_size:
                meta = {"heading": heading} if heading else {}
                results.append(ChunkResult(
                    content=content, level=level, position=pos, metadata=meta,
                ))
                pos += 1
            else:
                sub = fallback.chunk(body, {"chunk_size": chunk_size, "chunk_overlap": overlap})
                for i, sc in enumerate(sub):
                    meta = {"heading": heading} if heading else {}
                    if i == 0 and heading:
                        sc.content = f"{heading}\n\n{sc.content}"
                    sc.level = level
                    sc.position = pos
                    sc.metadata = meta
                    results.append(sc)
                    pos += 1

        return results

    @staticmethod
    def _clean_pdf_artifacts(text: str) -> str:
        text = _PAGE_NUM_RE.sub("", text)
        text = _PAGE_BREAK_RE.sub("\n\n", text)
        return text.strip()

    def _split_sections(self, text: str) -> list[tuple[str, int, str]]:
        lines = text.split("\n")
        sections: list[tuple[str, int, str]] = []
        current_heading = ""
        current_level = 0
        current_body: list[str] = []

        for line in lines:
            heading_match = self._detect_heading(line)
            if heading_match:
                # Flush previous section
                body_text = "\n".join(current_body).strip()
                if current_heading or body_text:
                    sections.append((current_heading, current_level, body_text))
                current_heading, current_level = heading_match
                current_body = []
            else:
                current_body.append(line)

        # Flush last section
        body_text = "\n".join(current_body).strip()
        if current_heading or body_text:
            sections.append((current_heading, current_level, body_text))

        return sections if sections else [("", 0, text)]

    @staticmethod
    def _detect_heading(line: str) -> tuple[str, int] | None:
        stripped = line.strip()
        if not stripped:
            return None

        # Numbered heading — derive level from numbering depth
        m = _NUMBERED_HEADING_RE.match(stripped)
        if m:
            depth = m.group(1).rstrip(".").count(".") + 1
            level = min(depth, 3)
            return stripped, level

        # Title-case short line (likely a section title)
        if len(stripped) <= 60 and _TITLECASE_RE.match(stripped):
            return stripped, 1

        return None
