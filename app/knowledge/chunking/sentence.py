import re

from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult

_SENTENCE_RE = re.compile(
    r"(?<=[.!?。！？])\s+|(?<=\n)\s*\n",
)


class SentenceStrategy(ChunkingStrategy):
    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        chunk_size = config.get("chunk_size", 500)
        sentences = _SENTENCE_RE.split(text)
        sentences = [s.strip() for s in sentences if s and s.strip()]

        results: list[ChunkResult] = []
        current = ""
        pos = 0

        for sent in sentences:
            candidate = f"{current} {sent}".strip() if current else sent
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    results.append(ChunkResult(content=current, level=0, position=pos))
                    pos += 1
                if len(sent) > chunk_size:
                    # Force-split oversized sentence
                    for i in range(0, len(sent), chunk_size):
                        results.append(ChunkResult(content=sent[i : i + chunk_size], level=0, position=pos))
                        pos += 1
                    current = ""
                else:
                    current = sent

        if current:
            results.append(ChunkResult(content=current, level=0, position=pos))

        return results
