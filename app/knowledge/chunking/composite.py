from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult


class CompositeStrategy(ChunkingStrategy):
    def __init__(self, primary: ChunkingStrategy, secondary: ChunkingStrategy):
        self.primary = primary
        self.secondary = secondary

    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        chunk_size = config.get("chunk_size", 500)
        primary_chunks = self.primary.chunk(text, config)
        results: list[ChunkResult] = []
        pos = 0

        for pc in primary_chunks:
            if len(pc.content) > chunk_size:
                sub = self.secondary.chunk(pc.content, config)
                for sc in sub:
                    sc.level = max(sc.level, pc.level)
                    sc.metadata = {**pc.metadata, **sc.metadata}
                    sc.position = pos
                    results.append(sc)
                    pos += 1
            else:
                pc.position = pos
                results.append(pc)
                pos += 1

        return results
