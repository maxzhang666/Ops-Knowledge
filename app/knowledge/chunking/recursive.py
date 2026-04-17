from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult


class RecursiveCharacterStrategy(ChunkingStrategy):
    SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []
        chunk_size = config.get("chunk_size", 500)
        overlap = config.get("chunk_overlap", 50)
        # Support custom delimiter: prepend to default separators
        separators = list(self.SEPARATORS)
        custom_delim = config.get("delimiter")
        if custom_delim:
            delim = custom_delim.replace("\\n", "\n").replace("\\t", "\t")
            if delim not in separators:
                separators.insert(0, delim)
        pieces = self._split_recursive(text, chunk_size, separators)
        pieces = self._apply_overlap(pieces, overlap)
        return [
            ChunkResult(content=p, level=0, position=i)
            for i, p in enumerate(pieces) if p.strip()
        ]

    def _split_recursive(
        self, text: str, chunk_size: int, separators: list[str],
    ) -> list[str]:
        if len(text) <= chunk_size:
            return [text]
        if not separators:
            return self._force_split(text, chunk_size)

        sep = separators[0]
        remaining_seps = separators[1:]

        if sep == "":
            return self._force_split(text, chunk_size)

        parts = text.split(sep)
        chunks: list[str] = []
        current = ""

        for part in parts:
            candidate = f"{current}{sep}{part}" if current else part
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                if len(part) > chunk_size:
                    chunks.extend(self._split_recursive(part, chunk_size, remaining_seps))
                    current = ""
                else:
                    current = part

        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _force_split(text: str, chunk_size: int) -> list[str]:
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    @staticmethod
    def _apply_overlap(pieces: list[str], overlap: int) -> list[str]:
        if overlap <= 0 or len(pieces) <= 1:
            return pieces
        result = [pieces[0]]
        for i in range(1, len(pieces)):
            prev_tail = pieces[i - 1][-overlap:]
            result.append(prev_tail + pieces[i])
        return result
