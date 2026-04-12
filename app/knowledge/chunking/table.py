import re

from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult
from app.knowledge.chunking.recursive import RecursiveCharacterStrategy

_TABLE_RE = re.compile(
    r"(\|.+\|\n\|[-:\s|]+\|\n(?:\|.+\|\n?)+)",
    re.MULTILINE,
)


class TableAwareStrategy(ChunkingStrategy):
    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        parts = self._split_tables(text)
        fallback = RecursiveCharacterStrategy()
        results: list[ChunkResult] = []
        pos = 0

        for content, is_table in parts:
            content = content.strip()
            if not content:
                continue
            if is_table:
                results.append(ChunkResult(
                    content=content, level=0, position=pos,
                    metadata={"type": "table"},
                ))
                pos += 1
            else:
                sub = fallback.chunk(content, config)
                for sc in sub:
                    sc.position = pos
                    results.append(sc)
                    pos += 1

        return results

    @staticmethod
    def _split_tables(text: str) -> list[tuple[str, bool]]:
        parts: list[tuple[str, bool]] = []
        last_end = 0
        for m in _TABLE_RE.finditer(text):
            if m.start() > last_end:
                parts.append((text[last_end : m.start()], False))
            parts.append((m.group(0), True))
            last_end = m.end()
        if last_end < len(text):
            parts.append((text[last_end:], False))
        return parts
