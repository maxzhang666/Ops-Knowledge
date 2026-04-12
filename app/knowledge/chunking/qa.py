import re

from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult
from app.knowledge.chunking.recursive import RecursiveCharacterStrategy

_QA_PATTERNS = [
    re.compile(r"^(?:Q|问|Question)\s*[:：]\s*", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\d+\.\s*(?:Q|问|Question)\s*[:：]?\s*", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^#{1,3}\s*(?:Q|问)\s*[:：]\s*", re.MULTILINE | re.IGNORECASE),
]

_ANSWER_RE = re.compile(r"^(?:A|答|Answer)\s*[:：]\s*", re.MULTILINE | re.IGNORECASE)


class QAPairStrategy(ChunkingStrategy):
    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        pairs = self._extract_pairs(text)
        if not pairs:
            return RecursiveCharacterStrategy().chunk(text, config)

        return [
            ChunkResult(
                content=pair, level=0, position=i,
                metadata={"type": "qa_pair"},
            )
            for i, pair in enumerate(pairs) if pair.strip()
        ]

    def _extract_pairs(self, text: str) -> list[str] | None:
        for pattern in _QA_PATTERNS:
            matches = list(pattern.finditer(text))
            if len(matches) >= 2:
                return self._split_at_matches(text, matches)
        return None

    @staticmethod
    def _split_at_matches(text: str, matches: list[re.Match]) -> list[str]:
        pairs: list[str] = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            pairs.append(text[start:end].strip())
        return pairs
