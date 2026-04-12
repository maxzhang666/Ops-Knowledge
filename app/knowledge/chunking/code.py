import re

from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult
from app.knowledge.chunking.recursive import RecursiveCharacterStrategy

_CODE_BLOCK_RE = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)


class CodeAwareStrategy(ChunkingStrategy):
    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        parts = self._split_code_blocks(text)
        fallback = RecursiveCharacterStrategy()
        results: list[ChunkResult] = []
        pos = 0

        for content, is_code in parts:
            content = content.strip()
            if not content:
                continue
            if is_code:
                lang = self._detect_lang(content)
                meta = {"type": "code"}
                if lang:
                    meta["language"] = lang
                results.append(ChunkResult(
                    content=content, level=0, position=pos, metadata=meta,
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
    def _split_code_blocks(text: str) -> list[tuple[str, bool]]:
        parts: list[tuple[str, bool]] = []
        last_end = 0
        for m in _CODE_BLOCK_RE.finditer(text):
            if m.start() > last_end:
                parts.append((text[last_end : m.start()], False))
            parts.append((m.group(0), True))
            last_end = m.end()
        if last_end < len(text):
            parts.append((text[last_end:], False))
        return parts

    @staticmethod
    def _detect_lang(block: str) -> str | None:
        first_line = block.split("\n", 1)[0]
        lang = first_line.removeprefix("```").strip()
        return lang if lang else None
