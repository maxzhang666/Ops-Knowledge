import re

from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult
from app.knowledge.chunking.recursive import RecursiveCharacterStrategy


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


class MarkdownStrategy(ChunkingStrategy):
    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        chunk_size = config.get("chunk_size", 500)
        overlap = config.get("chunk_overlap", 50)
        sections = self._split_by_headings(text)

        fallback = RecursiveCharacterStrategy()
        results: list[ChunkResult] = []
        pos = 0

        for heading, level, body in sections:
            content = f"{heading}\n\n{body}".strip() if heading else body.strip()
            if not content:
                continue
            if len(content) <= chunk_size:
                meta = {"heading": heading} if heading else {}
                results.append(ChunkResult(content=content, level=level, position=pos, metadata=meta))
                pos += 1
            else:
                sub_chunks = fallback.chunk(body, {"chunk_size": chunk_size, "chunk_overlap": overlap})
                for i, sc in enumerate(sub_chunks):
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
    def _split_by_headings(text: str) -> list[tuple[str, int, str]]:
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return [("", 0, text)]

        sections: list[tuple[str, int, str]] = []
        # Text before first heading
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append(("", 0, preamble))

        for i, m in enumerate(matches):
            level = len(m.group(1))  # 1-3
            heading = m.group(0)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            sections.append((heading, level, body))

        return sections
