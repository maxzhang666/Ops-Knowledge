from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChunkResult:
    content: str
    level: int = 0  # 0-3: document → section → subsection → paragraph
    position: int = 0
    metadata: dict = field(default_factory=dict)
    parent_chunk_id: str | None = None
    # Logical id used for parent-child linking. ONLY set by strategies that
    # produce hierarchical results (e.g. CompositeStrategy on the parent
    # row). Children reference it via parent_chunk_id; the ingestion task
    # maps both to the same real DB uuid so FK constraints hold.
    id: str | None = None


class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        ...

    def get_config_schema(self) -> dict:
        return {
            "chunk_size": {"type": "int", "default": 500, "min": 50, "max": 8000},
            "chunk_overlap": {"type": "int", "default": 50, "min": 0, "max": 500},
        }
